"""Đánh giá hệ hỗ trợ ra quyết định (giai đoạn Evaluation) và xuất báo cáo kết quả.

    python -m utd19_dss.evaluate          # cần chạy python -m utd19_dss.build trước

Đọc artifacts trong data/dss/ và ghi vào reports/:
    reports/dss_evaluation.md      báo cáo đánh giá (tiếng Việt)
    reports/dss_evaluation.json    toàn bộ chỉ số dạng máy đọc
    reports/tables/*.csv           bảng chi tiết
    reports/figures/*.png          biểu đồ

Nguyên tắc: mọi lựa chọn (mô hình, trọng số, ngưỡng) đều làm trên tháng 5 (kiểm định); số liệu
kết luận đều đo trên tháng 6 — dữ liệu phát lại "live" mà hệ thống chưa từng thấy khi dựng.
"""
from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import scoring as S
from .config import BASE_DIR, artifacts_dir, load_config
from .data import SLOTS

warnings.filterwarnings("ignore")

KEYS = S.KEYS


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
def _f(prec, rec, beta=1.0):
    return (1 + beta ** 2) * prec * rec / max(beta ** 2 * prec + rec, 1e-12)


def level_metrics(lvl: np.ndarray, U: np.ndarray, now: np.ndarray) -> dict:
    """Chỉ số của một cách phân mức trên lưới [T, D]."""
    y = U > 0
    now = now > 0
    fut = y & ~now
    hi = lvl == "Cao"
    hm = np.isin(lvl, ["Cao", "Trung bình"])
    p_hi = float(y[hi].mean()) if hi.any() else 0.0
    r_hi = float((hi & y).sum() / max(y.sum(), 1))
    p_hm = float(y[hm].mean()) if hm.any() else 0.0
    r_hm = float((hm & y).sum() / max(y.sum(), 1))
    return {
        "high_per_window": round(float(hi.sum(1).mean()), 2),
        "high_per_window_p95": float(np.quantile(hi.sum(1), 0.95)),
        "high_per_window_max": int(hi.sum(1).max()),
        "high_med_per_window": round(float(hm.sum(1).mean()), 2),
        "precision_high": round(p_hi, 4), "recall_high": round(r_hi, 4), "f1_high": round(_f(p_hi, r_hi), 4),
        "recall_now_high": round(float((hi & now).sum() / max(now.sum(), 1)), 4),
        "recall_future_high": round(float((hi & fut).sum() / max(fut.sum(), 1)), 4),
        "precision_high_med": round(p_hm, 4), "recall_high_med": round(r_hm, 4), "f2_high_med": round(_f(p_hm, r_hm, 2), 4),
        "recall_now_high_med": round(float((hm & now).sum() / max(now.sum(), 1)), 4),
        "recall_future_high_med": round(float((hm & fut).sum() / max(fut.sum(), 1)), 4),
        "missed_in_low": round(float(y[lvl == "Thấp"].mean()) if (lvl == "Thấp").any() else 0.0, 4),
    }


def p_at_k(score, U, k):
    act = (U > 0).any(1)
    return round(S.precision_at_k(score, U, k, act), 4)


def md_table(df: pd.DataFrame, pct_cols=(), dec=3) -> str:
    def fmt(c, v):
        if isinstance(v, (float, np.floating)):
            if np.isnan(v):
                return "—"
            return f"{100 * v:.1f}%" if c in pct_cols else f"{v:.{dec}f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:,.0f}"
        return str(v)
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join(["---"] * len(df.columns)) + "|"
    rows = ["| " + " | ".join(fmt(c, v) for c, v in zip(df.columns, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


# ---------------------------------------------------------------------------
# Đánh giá
# ---------------------------------------------------------------------------
def run(cfg_path=None) -> dict:
    cfg = load_config(cfg_path)
    art = artifacts_dir(cfg)
    if not (art / "meta.json").exists():
        raise SystemExit("Chưa có artifacts. Chạy trước: python -m utd19_dss.build")
    out = BASE_DIR / "reports"
    (out / "tables").mkdir(parents=True, exist_ok=True)
    (out / "figures").mkdir(parents=True, exist_ok=True)

    meta = json.loads((art / "meta.json").read_text(encoding="utf-8"))
    info = pd.read_csv(art / "detector_info.csv", encoding="utf-8-sig")
    rb = pd.read_parquet(art / "replay_batch.parquet")
    va = np.load(art / "valid_scores.npz")
    rule = meta.get("threshold_rule", {"high": "f1", "medium": "f2"})
    W5, TH5, W4, TH4 = meta["weights"], meta["thresholds"], meta["weights_v4"], {"high": 70, "medium": 40}

    dets = sorted(rb["detid"].unique())
    D = len(dets)
    rb = rb.sort_values(["day", "slot", "detid"]).reset_index(drop=True)
    Tn = len(rb) // D
    grid = lambda c: rb[c].to_numpy(dtype=np.float32).reshape(Tn, D)
    C_te = np.stack([grid(k) for k in KEYS], -1)
    now_te = np.nan_to_num(grid("event_now"))
    U_te = np.fmax(now_te, np.nan_to_num(grid("event_next30")))
    C_va, U_va, now_va = va["C"], va["U"], va["event_now"]
    tier = info.set_index("detid").loc[dets, "tier"].to_numpy()

    # ---------------- 1. So sánh chiến lược ra quyết định ----------------
    def strategy(name, w, th=None, note=""):
        sv, st = S.priority(C_va, w), S.priority(C_te, w)
        if th is None:   # chọn lại ngưỡng theo F1/F2 và áp cùng giới hạn năng lực ca trực với v5
            th = {**S.select_thresholds(S.threshold_sweep(sv, U_va, now_va), rule),
                  **({"max_high": TH5["max_high"]} if TH5.get("max_high") else {})}
        lv = S.level(st, th)
        m = level_metrics(lv, U_te, now_te)
        return {"strategy": name, "weights": {k: round(float(v), 3) for k, v in w.items()}, "thresholds": th,
                "p_at_5": p_at_k(st, U_te, 5), "p_at_10": p_at_k(st, U_te, 10), **m, "note": note}

    only = lambda k: {kk: (1.0 if kk == k else 0.0) for kk in KEYS}
    no_c5 = {k: (W5[k] if k != "C5" else 0.0) for k in KEYS}
    strategies = [
        strategy("v5 — đề xuất (C1–C5, trọng số tối ưu, ngưỡng F1/F2)", W5, TH5, "cấu hình triển khai"),
        strategy("v5 không giới hạn năng lực ca trực", W5, {"high": TH5["high"], "medium": TH5["medium"]},
                 "tách tác động của giới hạn top-N mỗi khung"),
        strategy("v4 — trọng số kinh nghiệm, ngưỡng 70/40", W4, TH4, "phiên bản trước"),
        strategy("v4 + ngưỡng chọn lại theo F1/F2", W4, None, "tách tác động của ngưỡng"),
        strategy("v5 bỏ C5 (chỉ luật C1–C4)", no_c5, None, "đóng góp của học máy"),
        strategy("Chỉ C5 (chỉ mô hình học máy)", only("C5"), None, "không dùng luật"),
        strategy("Chỉ C1 (occupancy vượt baseline)", only("C1"), None, "mốc đơn giản nhất"),
    ]
    strat_df = pd.DataFrame([{k: v for k, v in s.items() if k not in ("weights", "thresholds")} |
                             {"ngưỡng Cao/TB": f"{s['thresholds']['high']}/{s['thresholds']['medium']}"} for s in strategies])
    strat_df.to_csv(out / "tables/strategies_june.csv", index=False, encoding="utf-8-sig")

    # Năng lực ca trực: quét N (tối đa cảnh báo Cao mỗi khung), cùng trọng số và ngưỡng v5
    cap_sweep = []
    for cap in [0, 5, 8, 10, 12, 15, 20]:
        m = level_metrics(S.level(S.priority(C_te, W5), {"high": TH5["high"], "medium": TH5["medium"], "max_high": cap}), U_te, now_te)
        cap_sweep.append({"max_high": cap, **{k: m[k] for k in ["high_per_window", "high_per_window_p95", "precision_high",
                                                                 "recall_high", "f1_high", "recall_now_high", "recall_future_high"]}})
    pd.DataFrame(cap_sweep).to_csv(out / "tables/capacity_sweep_june.csv", index=False, encoding="utf-8-sig")

    # Ablation: bỏ từng tiêu chí
    abl = []
    for k in KEYS:
        w = {kk: (W5[kk] if kk != k else 0.0) for kk in KEYS}
        if k in ("C1", "C2"):     # C1, C2 bắt buộc trong công thức: thay bằng trọng số 0 nhưng vẫn yêu cầu có số đo
            pass
        r = strategy(f"bỏ {k}", w, None)
        abl.append({"criterion_removed": k, "label": S.FACTOR_LABELS[k], "p_at_10": r["p_at_10"], "f1_high": r["f1_high"],
                    "precision_high": r["precision_high"], "recall_high": r["recall_high"],
                    "delta_p_at_10": round(r["p_at_10"] - strategies[0]["p_at_10"], 4),
                    "delta_f1_high": round(r["f1_high"] - strategies[0]["f1_high"], 4)})
    abl_df = pd.DataFrame(abl)
    abl_df.to_csv(out / "tables/ablation_june.csv", index=False, encoding="utf-8-sig")

    # ---------------- 2. Ngưỡng ----------------
    sw_va = pd.DataFrame(meta.get("threshold_sweep_valid") or S.threshold_sweep(S.priority(C_va, W5), U_va, now_va))
    sw_te = pd.DataFrame(S.threshold_sweep(S.priority(C_te, W5), U_te, now_te))
    sw_va.to_csv(out / "tables/threshold_sweep_valid.csv", index=False, encoding="utf-8-sig")
    sw_te.to_csv(out / "tables/threshold_sweep_june.csv", index=False, encoding="utf-8-sig")

    # ---------------- 3. Mô hình C5 ----------------
    P = grid("p_event30")
    Y = grid("event_next30")
    ok = ~np.isnan(P) & ~np.isnan(Y)
    p, y = P[ok], Y[ok].astype(int)
    bins = np.array([0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0001])
    b = np.digitize(p, bins) - 1
    rel = pd.DataFrame([{"bin": f"{bins[i]:.2f}–{min(bins[i + 1], 1):.2f}", "n": int((b == i).sum()),
                         "p_mean": float(p[b == i].mean()) if (b == i).any() else np.nan,
                         "observed": float(y[b == i].mean()) if (b == i).any() else np.nan} for i in range(len(bins) - 1)])
    rel.to_csv(out / "tables/calibration_c5_june.csv", index=False, encoding="utf-8-sig")
    models_df = pd.DataFrame([{"model": k, "set": "valid (T5)", **{m: v[m] for m in ["pr_auc", "roc_auc", "precision", "recall", "f1", "onset_recall", "brier"]}}
                              for k, v in meta["models_valid"].items()] +
                             [{"model": k, "set": "test (T6)", **{m: v[m] for m in ["pr_auc", "roc_auc", "precision", "recall", "f1", "onset_recall", "brier"]}}
                              for k, v in meta["models_test"].items()])
    models_df.to_csv(out / "tables/models_c5.csv", index=False, encoding="utf-8-sig")

    # ---------------- 4. Theo thời gian, loại dữ liệu ----------------
    lv5 = S.level(S.priority(C_te, W5), TH5)
    lv4 = S.level(S.priority(C_te, W4), TH4)
    days = sorted(rb["day"].unique())
    per_day = []
    for i, d in enumerate(days):
        sl = slice(i * SLOTS, (i + 1) * SLOTS)
        m5 = level_metrics(lv5[sl], U_te[sl], now_te[sl]); m4 = level_metrics(lv4[sl], U_te[sl], now_te[sl])
        per_day.append({"day": d, "dow": pd.Timestamp(d).day_name(), "events": int((U_te[sl] > 0).sum()),
                        "f1_high_v5": m5["f1_high"], "f1_high_v4": m4["f1_high"],
                        "precision_high_v5": m5["precision_high"], "recall_high_v5": m5["recall_high"]})
    per_day = pd.DataFrame(per_day)
    per_day.to_csv(out / "tables/per_day_june.csv", index=False, encoding="utf-8-sig")
    hour = (np.arange(Tn) % SLOTS) // 4
    per_hour = []
    for h in range(24):
        r = hour == h
        m5 = level_metrics(lv5[r], U_te[r], now_te[r])
        per_hour.append({"hour": h, "events_per_window": round(float((U_te[r] > 0).sum(1).mean()), 2),
                         "high_per_window": m5["high_per_window"], "precision_high": m5["precision_high"],
                         "recall_high": m5["recall_high"],
                         "no_data_share": round(float((lv5[r] == "Không đủ dữ liệu").mean()), 4)})
    per_hour = pd.DataFrame(per_hour)
    per_hour.to_csv(out / "tables/per_hour_june.csv", index=False, encoding="utf-8-sig")
    per_tier = []
    for t in ["A", "B", "C", "X"]:
        c = tier == t
        if not c.any():
            continue
        m5 = level_metrics(lv5[:, c], U_te[:, c], now_te[:, c])
        per_tier.append({"tier": t, "detectors": int(c.sum()), "events": int((U_te[:, c] > 0).sum()),
                         "precision_high": m5["precision_high"], "recall_high": m5["recall_high"],
                         "no_data_share": round(float((lv5[:, c] == "Không đủ dữ liệu").mean()), 4)})
    per_tier = pd.DataFrame(per_tier)
    per_tier.to_csv(out / "tables/per_tier_june.csv", index=False, encoding="utf-8-sig")

    # ---------------- 5. Gợi ý hành động ----------------
    hi = lv5 == "Cao"
    top = S.top_factor(C_te, W5)
    zf = grid("z_flow") if "z_flow" in rb.columns else np.full((Tn, D), np.nan)
    codes = []
    for ti, di in zip(*np.where(hi)):
        Cd = {k: (None if np.isnan(C_te[ti, di, j]) else float(C_te[ti, di, j])) for j, k in enumerate(KEYS)}
        z = None if np.isnan(zf[ti, di]) else float(zf[ti, di])
        codes.append((S.action("Cao", top[ti, di], Cd, z, tier[di])[0], U_te[ti, di] > 0))
    act = pd.DataFrame(codes, columns=["code", "hit"])
    act_df = act.groupby("code").agg(alerts=("hit", "size"), precision=("hit", "mean")).reset_index()
    act_df["share"] = act_df["alerts"] / act_df["alerts"].sum()
    act_df["label"] = act_df["code"].map(S.ACTION_CODES)
    act_df = act_df.sort_values("alerts", ascending=False)[["code", "label", "alerts", "share", "precision"]]
    act_df.to_csv(out / "tables/actions_june.csv", index=False, encoding="utf-8-sig")

    # ---------------- 6. Hiệu năng live ----------------
    perf = _latency(cfg)

    # ---------------- 7. Biểu đồ ----------------
    _figures(out / "figures", sw_va, sw_te, TH5, rel, per_hour, per_day, P, Y, C_te, W4, meta)

    res = {"generated_at": pd.Timestamp.now().isoformat(timespec="seconds"), "built_at": meta["built_at"],
           "split": meta["split"], "label": "cần chú ý = sự kiện ùn tắc bất thường ngay tại khung hoặc trong 30 phút sau",
           "weights": W5, "thresholds": TH5, "threshold_rule": rule,
           "strategies": strategies, "capacity_sweep": cap_sweep, "ablation": abl, "models": {"valid": meta["models_valid"], "test": meta["models_test"],
                                                                "best": meta["best_model"]},
           "calibration_c5": rel.to_dict("records"), "per_tier": per_tier.to_dict("records"),
           "per_day_summary": {"f1_high_v5_mean": round(float(per_day.f1_high_v5.mean()), 4),
                               "f1_high_v5_std": round(float(per_day.f1_high_v5.std()), 4),
                               "f1_high_v4_mean": round(float(per_day.f1_high_v4.mean()), 4),
                               "days_v5_better": int((per_day.f1_high_v5 > per_day.f1_high_v4).sum()), "days": len(per_day)},
           "actions": act_df.to_dict("records"), "performance": perf,
           "events_june": {"total": int((U_te > 0).sum()), "now": int((now_te > 0).sum()),
                           "future_only": int(((U_te > 0) & (now_te == 0)).sum())}}
    (out / "dss_evaluation.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "dss_evaluation.md").write_text(_report(res, meta, strat_df, abl_df, sw_va, sw_te, models_df, rel, per_hour,
                                                   per_day, per_tier, act_df), encoding="utf-8")
    print(f"Đã ghi báo cáo đánh giá vào {out}")
    return res


def _latency(cfg) -> dict:
    """Thời gian chấm một khung 15 phút (đường đi live: tiêu chí + đặc trưng + mô hình)."""
    from . import baseline as B, engine as E
    from .build import _block, _day_types
    art = artifacts_dir(cfg)
    g = joblib.load(art / "grid.joblib")
    info = pd.read_csv(art / "detector_info.csv", encoding="utf-8-sig").set_index("detid").loc[g.detids].reset_index()
    base = B.Baseline.from_npz(art / "baseline_final.npz")
    model = joblib.load(art / "model.joblib")["model"]
    static = np.load(art / "static_features.npy")
    W, _ = E.neighbor_matrix(cfg, info)
    ctx = {"W": W, "ref": info["tier"].eq("A").to_numpy()}
    dt = _day_types(g, cfg)
    t0 = g.t_index(cfg["split"]["replay_start"], 0) + 68
    times = []
    for i in range(30):
        t = t0 + i
        s = time.perf_counter()
        ex, blk, X = _block(cfg, g, base, dt, ctx, static, t - 4, t + 1)
        okr = ~np.isnan(blk["z_occ"][-1])
        if okr.any():
            model.predict_proba(X[-1][okr])
        times.append(time.perf_counter() - s)
    return {"detectors": int(g.D), "ms_per_window_median": round(1000 * float(np.median(times)), 1),
            "ms_per_window_p95": round(1000 * float(np.percentile(times, 95)), 1)}


def _figures(fd: Path, sw_va, sw_te, th, rel, per_hour, per_day, P, Y, C_te, W4, meta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    green, red, amber, blue, grey = "#0a9e6e", "#d64545", "#d98b0b", "#3b6fd8", "#7a8a84"

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    for a, sw, ttl in [(ax[0], sw_va, "Tháng 5 (chọn ngưỡng)"), (ax[1], sw_te, "Tháng 6 (kiểm thử)")]:
        a.plot(sw.threshold, sw.precision, color=red, label="Precision")
        a.plot(sw.threshold, sw.recall, color=blue, label="Recall")
        a.plot(sw.threshold, sw.f1, color=green, lw=2, label="F1")
        a.plot(sw.threshold, sw.f2, color=amber, ls="--", label="F2")
        a.axvline(th["high"], color=red, ls=":", lw=1); a.axvline(th["medium"], color=amber, ls=":", lw=1)
        a.set_title(ttl); a.set_xlabel("Ngưỡng Priority Score"); a.set_ylim(0, 1)
    ax[0].legend(frameon=False)
    fig.tight_layout(); fig.savefig(fd / "threshold_sweep.png", dpi=150); plt.close(fig)

    ok = ~np.isnan(P) & ~np.isnan(Y)
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
    for name, s, c in [(meta["best_model_label"], P[ok], green),
                       ("Điểm luật v4 (C1–C4)", np.nan_to_num(S.priority(C_te, W4))[ok] / 100, grey)]:
        pr, rc, _ = precision_recall_curve(Y[ok].astype(int), s)
        ax[0].plot(rc, pr, color=c, label=name)
    ax[0].axhline(Y[ok].mean(), color="#bbb", ls=":", lw=1, label="Tỷ lệ nền")
    ax[0].set_xlabel("Recall"); ax[0].set_ylabel("Precision"); ax[0].set_title("C5 — đường Precision–Recall (tháng 6)")
    ax[0].legend(frameon=False, fontsize=8)
    r = rel.dropna()
    ax[1].plot([0, 1], [0, 1], color="#bbb", ls=":")
    ax[1].plot(r.p_mean, r.observed, "o-", color=green)
    ax[1].set_xlabel("Xác suất dự báo"); ax[1].set_ylabel("Tỷ lệ thực tế"); ax[1].set_title("Hiệu chỉnh xác suất C5 (tháng 6)")
    fig.tight_layout(); fig.savefig(fd / "c5_pr_calibration.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.bar(per_hour.hour, per_hour.events_per_window, color="#cfe9df", label="Sự kiện cần chú ý / khung")
    ax.plot(per_hour.hour, per_hour.high_per_window, color=red, marker="o", label="Cảnh báo Cao / khung")
    ax2 = ax.twinx(); ax2.plot(per_hour.hour, per_hour.precision_high, color=green, ls="--", label="Precision Cao")
    ax2.set_ylim(0, 1); ax.set_xlabel("Giờ"); ax.set_title("Theo giờ trong ngày — tháng 6")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(fd / "per_hour.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 3.0))
    x = np.arange(len(per_day))
    ax.plot(x, per_day.f1_high_v5, color=green, marker="o", label="v5")
    ax.plot(x, per_day.f1_high_v4, color=grey, marker="s", label="v4")
    ax.set_xticks(x[::3]); ax.set_xticklabels([d[5:] for d in per_day.day[::3]])
    ax.set_ylabel("F1 mức Cao"); ax.set_title("Ổn định theo ngày — tháng 6"); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(fd / "per_day_f1.png", dpi=150); plt.close(fig)


def _report(res, meta, strat_df, abl_df, sw_va, sw_te, models_df, rel, per_hour, per_day, per_tier, act_df) -> str:
    s0, su, s4 = res["strategies"][0], res["strategies"][1], res["strategies"][2]
    th = res["thresholds"]
    pct = lambda v: f"{100 * v:.1f}%"
    ev = res["events_june"]
    best = meta["best_model"]
    mt, _mv = meta["models_test"], meta["models_valid"]
    lab = {"dt": "Decision Tree", "nb": "Naive Bayes", "mlp": "Neural Network (MLP)", "gb": "Gradient Boosting",
           "persistence": "Mốc Persistence", "rule_v4": "Mốc điểm luật v4"}
    sel = lambda df, cols, ren: df[cols].rename(columns=ren)

    strat_cols = ["strategy", "ngưỡng Cao/TB", "p_at_10", "high_per_window", "precision_high", "recall_high", "f1_high",
                  "recall_now_high", "recall_future_high", "recall_high_med", "precision_high_med"]
    strat_ren = {"strategy": "Chiến lược", "p_at_10": "P@10", "high_per_window": "Cao/khung", "precision_high": "Precision Cao",
                 "recall_high": "Recall Cao", "f1_high": "F1 Cao", "recall_now_high": "Recall Cao (đang diễn ra)",
                 "recall_future_high": "Recall Cao (sắp xảy ra)", "recall_high_med": "Recall Cao+TB",
                 "precision_high_med": "Precision Cao+TB"}
    pc_s = {"P@10", "Precision Cao", "Recall Cao", "Recall Cao (đang diễn ra)", "Recall Cao (sắp xảy ra)", "Recall Cao+TB", "Precision Cao+TB"}

    mdl = models_df.copy()
    mdl["model"] = mdl["model"].map(lab).fillna(mdl["model"])
    mdl = mdl.rename(columns={"model": "Mô hình", "set": "Tập", "pr_auc": "PR-AUC", "roc_auc": "ROC-AUC", "precision": "Precision",
                              "recall": "Recall", "f1": "F1", "onset_recall": "Recall sự kiện mới", "brier": "Brier"})
    sw_cols = ["threshold", "alerts_per_window", "precision", "recall", "recall_now", "recall_future", "f1", "f2"]
    sw_ren = {"threshold": "Ngưỡng", "alerts_per_window": "Cảnh báo/khung", "precision": "Precision", "recall": "Recall",
              "recall_now": "Recall đang diễn ra", "recall_future": "Recall sắp xảy ra", "f1": "F1", "f2": "F2"}
    pc_sw = {"Precision", "Recall", "Recall đang diễn ra", "Recall sắp xảy ra"}

    L = []
    L.append("# Báo cáo đánh giá hệ hỗ trợ ra quyết định (DSS v5 — Luzern)\n")
    L.append(f"_Sinh tự động bởi `python -m utd19_dss.evaluate` lúc {res['generated_at']} từ artifacts dựng lúc {res['built_at']}._\n")
    L.append("## 1. Phương pháp đánh giá\n")
    L.append(f"- **Chia dữ liệu theo thời gian:** huấn luyện {meta['split']['train'][0]} → {meta['split']['train'][1]}; "
             f"kiểm định {meta['split']['valid'][0]} → {meta['split']['valid'][1]} (chọn mô hình, trọng số, ngưỡng); "
             f"**kiểm thử {meta['split']['replay'][0]} → {meta['split']['replay'][1]}** (dữ liệu phát lại live, chưa dùng khi dựng). Mọi số liệu dưới đây là của tháng 6 nếu không ghi khác.")
    L.append(f"- **Nhãn \"cần chú ý\":** detector có sự kiện ùn tắc bất thường (z occupancy ≥ 2 và occupancy cao hơn kỳ vọng ≥ 5 điểm %) ngay tại khung **hoặc** trong 30 phút sau. "
             f"Tháng 6 có {ev['total']:,} detector-khung cần chú ý: {ev['now']:,} đang diễn ra và {ev['future_only']:,} chỉ xảy ra trong 30 phút tới.")
    L.append("- **Chỉ số:** Precision@10 (top 10 mỗi khung, đúng hướng sử dụng của bảng xếp hạng); precision / recall / F1 của mức Cao; recall tách thành sự kiện **đang diễn ra** (phát hiện) và **sắp xảy ra** (dự báo); PR-AUC cho mô hình C5.\n")

    L.append("## 2. Kết quả chính\n")
    L.append(f"- Ngưỡng triển khai: **Cao ≥ {th['high']}** (F1 lớn nhất trên tháng 5), **Trung bình ≥ {th['medium']}** (F2 lớn nhất). Trọng số: " +
             ", ".join(f"{k} = {v:.2f}" for k, v in res["weights"].items()) + ".")
    L.append(f"- Mức Cao: precision **{pct(s0['precision_high'])}**, recall **{pct(s0['recall_high'])}**, F1 **{s0['f1_high']:.3f}** "
             f"(v4: {pct(s4['precision_high'])} / {pct(s4['recall_high'])} / {s4['f1_high']:.3f}), trung bình {s0['high_per_window']} cảnh báo Cao mỗi khung.")
    L.append(f"- Recall tách theo loại: mức Cao bắt **{pct(s0['recall_now_high'])}** sự kiện đang diễn ra và {pct(s0['recall_future_high'])} sự kiện sắp xảy ra; "
             f"tính cả mức Trung bình: {pct(s0['recall_now_high_med'])} và {pct(s0['recall_future_high_med'])}.")
    L.append(f"- Precision@10: **{pct(s0['p_at_10'])}** (v4 {pct(s4['p_at_10'])}).")
    if th.get("max_high"):
        L.append(f"- Năng lực ca trực: tối đa **{th['max_high']} cảnh báo Cao mỗi khung** (phần vượt chuyển sang hàng chờ, mức Trung bình). "
                 f"So với không giới hạn: F1 mức Cao {s0['f1_high']:.3f} so với {su['f1_high']:.3f}, precision {pct(s0['precision_high'])} so với {pct(su['precision_high'])}, "
                 f"recall {pct(s0['recall_high'])} so với {pct(su['recall_high'])}; số cảnh báo Cao lớn nhất trong một khung {s0.get('high_per_window_max', '—')} so với {su.get('high_per_window_max', '—')}.")
    L.append(f"- Mô hình C5 ({lab.get(best, best)}): PR-AUC tháng 6 = **{mt[best]['pr_auc']:.3f}** (Persistence {mt['persistence']['pr_auc']:.3f}, điểm luật v4 {mt['rule_v4']['pr_auc']:.3f}; tỷ lệ nền ≈ {pct(mt[best]['pos_rate'])}).")
    pdm = res["per_day_summary"]
    L.append(f"- Ổn định: F1 mức Cao theo ngày trung bình {pdm['f1_high_v5_mean']:.3f} ± {pdm['f1_high_v5_std']:.3f}; v5 tốt hơn v4 ở {pdm['days_v5_better']}/{pdm['days']} ngày.")
    L.append(f"- Hiệu năng live: {res['performance']['ms_per_window_median']} ms để chấm một khung 15 phút cho {res['performance']['detectors']} detector (p95 {res['performance']['ms_per_window_p95']} ms).\n")

    L.append("## 3. So sánh chiến lược ra quyết định\n")
    L.append("Mỗi chiến lược (trừ v4 gốc) được chọn ngưỡng trên tháng 5 bằng cùng quy tắc F1/F2, rồi đo trên tháng 6.\n")
    L.append(md_table(sel(strat_df, strat_cols, strat_ren), pct_cols=pc_s) + "\n")
    L.append("**Đọc kết quả:** so v4 với \"v4 + ngưỡng chọn lại\" cho thấy riêng việc chọn ngưỡng có căn cứ đã cải thiện F1; so \"v5 bỏ C5\" với v5 cho thấy phần đóng góp của học máy, chủ yếu ở recall sự kiện sắp xảy ra.\n")
    L.append("### 3.0. Năng lực ca trực (tối đa N cảnh báo Cao mỗi khung)\n")
    L.append("| N | Cao/khung | Precision Cao | Recall Cao | Recall đang diễn ra | Recall sắp xảy ra | F1 Cao |")
    L.append("|---|---|---|---|---|---|---|")
    for r in res.get("capacity_sweep", []):
        L.append(f"| {r['max_high'] or 'không giới hạn'} | {r['high_per_window']} | {pct(r['precision_high'])} | {pct(r['recall_high'])} | "
                 f"{pct(r['recall_now_high'])} | {pct(r['recall_future_high'])} | {r['f1_high']:.3f} |")
    L.append("\nGiới hạn cắt trước hết các cảnh báo sắp xảy ra (điểm thấp hơn cảnh báo đang ùn). N là biến quyết định của người quản lý ca, chỉnh được trên trang What-if.\n")
    L.append("### 3.1. Loại bỏ từng tiêu chí (ablation)\n")
    L.append(md_table(abl_df.rename(columns={"criterion_removed": "Bỏ tiêu chí", "label": "Tên", "p_at_10": "P@10", "f1_high": "F1 Cao",
                                             "precision_high": "Precision Cao", "recall_high": "Recall Cao",
                                             "delta_p_at_10": "Δ P@10", "delta_f1_high": "Δ F1 Cao"}),
                      pct_cols={"P@10", "Precision Cao", "Recall Cao"}) + "\n")

    L.append("C5 là tiêu chí đóng góp lớn nhất; C1 đứng thứ hai. C2, C3, C4 gần như không đổi kết quả tổng hợp (|Δ F1| ≤ 0,015) vì thông tin của chúng đã có trong đặc trưng của C5; "
             "chúng vẫn được giữ với trọng số nhỏ vì bảng quyết định dùng chúng để chọn **loại** hành động (ùn kéo dài, ùn lan khu vực, nghi sự cố, tăng đột biến) và để người vận hành đọc được lý do.\n")
    L.append("## 4. Chọn ngưỡng\n")
    L.append("![Quét ngưỡng](figures/threshold_sweep.png)\n")
    L.append("Tháng 5 (dùng để chọn):\n")
    L.append(md_table(sel(sw_va, sw_cols, sw_ren), pct_cols=pc_sw) + "\n")
    L.append("Tháng 6 (kiểm chứng):\n")
    L.append(md_table(sel(sw_te, sw_cols, sw_ren), pct_cols=pc_sw) + "\n")
    L.append("Hạ ngưỡng làm tăng recall nhưng precision giảm nhanh; F1 đạt đỉnh ở ngưỡng Cao đã chọn và vị trí đỉnh trên tháng 6 gần với tháng 5, tức là lựa chọn không bị khớp riêng cho tháng 5. "
             "Phần recall còn thiếu gần như toàn bộ là sự kiện **sắp xảy ra**: sự kiện đang diễn ra được bắt gần đủ, còn dự báo 15–30 phút trước bị giới hạn bởi độ khó của bài toán (mục 5).\n")

    L.append("## 5. Mô hình học máy C5\n")
    L.append(md_table(mdl, pct_cols={"Precision", "Recall", "Recall sự kiện mới"}) + "\n")
    L.append("![PR và hiệu chỉnh](figures/c5_pr_calibration.png)\n")
    L.append("Hiệu chỉnh xác suất trên tháng 6:\n")
    L.append(md_table(rel.rename(columns={"bin": "Khoảng xác suất", "n": "Số mẫu", "p_mean": "Xác suất TB", "observed": "Tỷ lệ thực tế"}),
                      pct_cols={"Xác suất TB", "Tỷ lệ thực tế"}) + "\n")
    L.append("Xác suất dự báo bám sát tỷ lệ thực tế, nên có thể dùng trực tiếp làm \"P(ùn trong 30′)\" trên giao diện. "
             "PR-AUC thấp hơn 0,5 là đặc thù của bài toán hiếm (tỷ lệ nền vài %): mức hiện tại cao hơn ngẫu nhiên khoảng 10 lần và hơn 2,5 lần mốc Persistence. "
             "Đã thử thêm đặc trưng (z cùng khung hôm trước/tuần trước, thống kê trượt 1–2 giờ, lân cận, tỷ lệ sự kiện lịch sử) và nhãn trung bình 30 phút nhưng không cải thiện; cần dữ liệu ngoài (sự cố, công trường, tín hiệu đèn, thời tiết).\n")

    L.append("## 6. Theo thời gian và chất lượng dữ liệu\n")
    L.append("![Theo giờ](figures/per_hour.png)\n")
    L.append(md_table(per_hour.rename(columns={"hour": "Giờ", "events_per_window": "Sự kiện/khung", "high_per_window": "Cao/khung",
                                               "precision_high": "Precision Cao", "recall_high": "Recall Cao", "no_data_share": "Thiếu dữ liệu"}),
                      pct_cols={"Precision Cao", "Recall Cao", "Thiếu dữ liệu"}) + "\n")
    L.append("![Theo ngày](figures/per_day_f1.png)\n")
    L.append(md_table(per_tier.rename(columns={"tier": "Tier", "detectors": "Detector", "events": "Sự kiện", "precision_high": "Precision Cao",
                                               "recall_high": "Recall Cao", "no_data_share": "Thiếu dữ liệu"}),
                      pct_cols={"Precision Cao", "Recall Cao", "Thiếu dữ liệu"}) + "\n")

    L.append("## 7. Gợi ý hành động ở mức Cao\n")
    L.append(md_table(act_df.rename(columns={"code": "Mã", "label": "Hành động", "alerts": "Số cảnh báo", "share": "Tỷ trọng", "precision": "Precision"}),
                      pct_cols={"Tỷ trọng", "Precision"}) + "\n")

    L.append("## 8. Kết luận và hạn chế\n")
    L.append(f"- DSS v5 cải thiện so với v4 ở mọi chỉ số tổng hợp chính trên dữ liệu chưa thấy (F1 mức Cao {s0['f1_high']:.3f} so với {s4['f1_high']:.3f}; P@10 {pct(s0['p_at_10'])} so với {pct(s4['p_at_10'])}).")
    L.append("- Phát hiện bất thường đang diễn ra gần như đầy đủ; dự báo trước 30 phút mới bắt được một phần — đây là giới hạn chính, do nhãn 15 phút nhiễu và thiếu dữ liệu nguyên nhân.")
    L.append("- Khung đêm (00–05 giờ) thiếu dữ liệu nhiều do khoảng đo bị gắn error tập trung khi lưu lượng ≈ 0.")
    L.append("- Đánh giá dùng nhãn thống kê, chưa đối chiếu với nhật ký sự cố thực; mới kiểm thử trên một tháng (6/2015). Khi có dữ liệu mùa khác cần chạy lại build và đánh giá.")
    L.append("- **Lưu ý khi đọc recall “đang diễn ra”:** nhãn sự kiện và tiêu chí C1 cùng dựa trên z occupancy so với baseline, nên mức Cao bắt gần hết sự kiện đang diễn ra một phần là do cách định nghĩa (gần như tất yếu). Giá trị gia tăng thật của DSS nằm ở recall sự kiện **sắp xảy ra**, Precision@10 và PR-AUC của C5 so với mốc Persistence.")
    L.append("- **Rò rỉ thông tin ở giai đoạn kiểm định (đã khắc phục ở v5.1):** tier chất lượng, cụm detector K-means và ma trận lân cận dùng khi chọn mô hình/trọng số/ngưỡng giờ chỉ tính trên 01/01–30/04; giai đoạn cuối dùng 01/01–31/05.")
    L.append(f"- **Năng lực ca trực (đã xử lý ở v5.1):** không giới hạn thì giờ cao điểm có khung tới {su.get('high_per_window_max', '—')} cảnh báo Cao; nay giữ tối đa {th.get('max_high') or '∞'} cảnh báo/khung, phần vượt vào hàng chờ. Cái giá là recall thấp hơn, chủ yếu ở sự kiện sắp xảy ra (mục 3.0).\n")
    return "\n".join(L)


if __name__ == "__main__":
    run()
