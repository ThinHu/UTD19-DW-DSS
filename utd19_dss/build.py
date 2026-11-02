"""Dựng toàn bộ thành phần offline của DSS (chạy 1 lần trước khi mở API).

    python -m utd19_dss.build            # hoặc: make dss-build

Các bước:
  1. Nạp dữ liệu từ DW (mart.dss_detector_window) hoặc CSV, áp luật chất lượng dữ liệu, chia tier.
  2. K-means: phân cụm ngày (xác nhận loại ngày cho baseline) và phân cụm detector (hành vi).
  3. Giai đoạn kiểm định: baseline từ 01/01–30/04, huấn luyện DT / NB / MLP, đánh giá trên tháng 5,
     chọn mô hình, tối ưu trọng số và hiệu chỉnh ngưỡng trên tháng 5.
  4. Giai đoạn cuối: baseline từ 01/01–31/05, huấn luyện lại mô hình đã chọn, chấm tháng 6
     (dữ liệu phát lại live) và ghi lại chỉ số kiểm thử ngoài mẫu.
  5. Lưu artifacts vào data/dss/ cho API.
"""
from __future__ import annotations

import json
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.tree import export_text

from . import baseline as B
from . import engine as E
from . import models as M
from . import scoring as S
from .config import artifacts_dir, load_config
from .data import SLOTS, build_grid, load_detectors, load_windows

warnings.filterwarnings("ignore", category=RuntimeWarning)

V4_WEIGHTS = {"C1": 0.45, "C2": 0.20, "C3": 0.25, "C4": 0.10, "C5": 0.0}


def to_c5(p, cfg):
    return (np.minimum(p / cfg["event"]["c5_p_cap"], 1.0) * 100).astype(np.float32)


def log(msg):
    print(msg, flush=True)


def _day_types(grid, cfg):
    hol = set(cfg["calendar"]["holidays"])
    return np.array([B.calendar_day_type(d, hol) for d in grid.days])


def _block(cfg, grid, base, day_type, ctx, static, t0, t1):
    """Tính tiêu chí + đặc trưng cho [t0, t1) — dùng chung cho build và live."""
    ex = B.expected(cfg, base, grid, day_type, t0, t1)
    t_hi = min(t1 + 2, grid.T)
    ex2 = B.expected(cfg, base, grid, day_type, t0 + 2, t_hi)
    mu2 = np.full_like(ex["mu_occ"], np.nan)
    mu2[: t_hi - t0 - 2] = ex2["mu_occ"]
    occ, flow = grid.occ[t0:t1], grid.flow[t0:t1]
    blk = E.compute_block(cfg, occ, flow, ex, ctx)
    t_abs = np.arange(t0, t1)
    X = E.build_features(blk, ex, mu2, occ, flow, grid.err_ratio[t0:t1], t_abs,
                         E.day_type_rows(day_type, t_abs), static)
    return ex, blk, X


def _profile(grid, windows, src, day_type) -> dict:
    info = grid.info
    dow = pd.to_datetime(pd.Series(grid.days)).dt.day_of_week.value_counts().sort_index()
    names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    err_bins = pd.cut(info["error_pct"], [-0.01, 5, 25, 50, 90, 100],
                      labels=["≤5%", "5–25%", "25–50%", "50–90%", ">90%"]).value_counts().sort_index()
    return {
        "source": src,
        "rows": int(len(windows)),
        "detectors": int(grid.D),
        "days": len(grid.days),
        "first_day": grid.days[0], "last_day": grid.days[-1],
        "dow_counts": {names[i]: int(dow.get(i, 0)) for i in range(7)},
        "day_type_counts": {k: int((day_type == k).sum()) for k in B.DAY_TYPES},
        "tiers": info["tier"].value_counts().reindex(["A", "B", "C", "X"], fill_value=0).astype(int).to_dict(),
        "error_bins": {str(k): int(v) for k, v in err_bins.items()},
        "error_median": round(float(info["error_pct"].median()), 2),
        "error_rows_pct": round(float(100 * windows["n_err"].sum() / windows["n"].sum()), 2),
        "dropped": grid.dropped,
        "fclass": info["fclass"].value_counts().astype(int).to_dict(),
        "full_days_detectors": int((info["days_with_data"] >= 151).sum()),
        "mean_flow_quantiles": {q: round(float(info["mean_flow"].quantile(q)), 1) for q in [0.25, 0.5, 0.75, 1.0]},
        "mean_occ_quantiles": {q: round(float(info["mean_occ"].quantile(q)), 4) for q in [0.0, 0.5, 1.0]},
    }


def _spatial_corr(grid, ex, blk, t_end, dist) -> list[dict]:
    ref = grid.info["tier"].eq("A").to_numpy()
    r = (blk["occ_n"] - ex["mu_occ"])[:t_end][:, ref]
    keep = np.mean(~np.isnan(r), 0) > 0.6
    r = r[:, keep]
    d = dist[np.ix_(np.where(ref)[0][keep], np.where(ref)[0][keep])]
    df = pd.DataFrame(r)
    C = df.corr(min_periods=2000).to_numpy()
    iu = np.triu_indices_from(C, 1)
    dd, cc = d[iu], C[iu]
    bins = [(0, 0.05, "< 50 m"), (0.05, 0.25, "50–250 m"), (0.25, 0.5, "0,25–0,5 km"),
            (0.5, 1.0, "0,5–1 km"), (1.0, 2.0, "1–2 km"), (2.0, 99, "> 2 km")]
    out = []
    for lo, hi, lab in bins:
        m = (dd >= lo) & (dd < hi) & ~np.isnan(cc)
        out.append({"bin": lab, "pairs": int(m.sum()), "mean": round(float(cc[m].mean()), 3) if m.any() else None,
                    "median": round(float(np.median(cc[m])), 3) if m.any() else None})
    return out


def _level_stats(score, lvl, target, event_now=None) -> dict:
    s = lvl.ravel()
    y = np.nan_to_num(target).ravel()
    out = {"dist": {}, "precision": {}}
    for L in S.LEVELS:
        m = s == L
        out["dist"][L] = round(float(m.mean() * 100), 2)
        if L != "Không đủ dữ liệu" and m.any():
            out["precision"][L] = round(float(y[m].mean()), 4)
    ev = (np.nan_to_num(target) > 0)
    out["event_recall_high"] = round(float(((lvl == "Cao") & ev).sum() / max(ev.sum(), 1)), 4)
    out["event_recall_high_med"] = round(float((np.isin(lvl, ["Cao", "Trung bình"]) & ev).sum() / max(ev.sum(), 1)), 4)
    if event_now is not None:
        now = np.nan_to_num(event_now) > 0
        fut = ev & ~now
        hi, hm = lvl == "Cao", np.isin(lvl, ["Cao", "Trung bình"])
        out["recall_now_high"] = round(float((hi & now).sum() / max(now.sum(), 1)), 4)
        out["recall_future_high"] = round(float((hi & fut).sum() / max(fut.sum(), 1)), 4)
        out["recall_now_high_med"] = round(float((hm & now).sum() / max(now.sum(), 1)), 4)
        out["recall_future_high_med"] = round(float((hm & fut).sum() / max(fut.sum(), 1)), 4)
        out["events_now"], out["events_future_only"] = int(now.sum()), int(fut.sum())
    high = (lvl == "Cao").sum(1)
    out["high_per_window_mean"] = round(float(high.mean()), 2)
    out["windows_with_high_pct"] = round(float((high > 0).mean() * 100), 1)
    out["windows_with_10plus_high_pct"] = round(float((high >= 10).mean() * 100), 1)
    out["high_per_window_max"] = int(high.max())
    return out


def run(cfg_path=None):
    t_start = time.time()
    cfg = load_config(cfg_path)
    out_dir = artifacts_dir(cfg)
    rs = cfg["ml"]["random_state"]

    log("[1/6] Nạp dữ liệu và dựng lưới ...")
    windows, src = load_windows(cfg)
    det = load_detectors(cfg)
    grid = build_grid(cfg, windows, det)                     # giai đoạn cuối: lịch sử tới 31/05
    valid_start = (pd.Timestamp(cfg["split"]["train_end"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    gridV = build_grid(cfg, windows, det, hist_end=valid_start)  # giai đoạn kiểm định: chỉ lịch sử tới 30/04
    day_type = _day_types(grid, cfg)
    t_val0 = grid.t_index(pd.Timestamp(cfg["split"]["train_end"]).strftime("%Y-%m-%d"), 0) + SLOTS
    t_rep0 = grid.t_index(cfg["split"]["replay_start"], 0)
    T = grid.T
    log(f"      nguồn: {src}; {grid.D} detector × {len(grid.days)} ngày; tier: "
        f"{grid.info['tier'].value_counts().to_dict()}")
    profile = _profile(grid, windows, src, day_type)

    log("[2/6] K-means: phân cụm ngày và phân cụm detector ...")
    kd = B.kmeans_day_types(cfg, grid, t_rep0)
    kdet = B.kmeans_detectors(cfg, grid, day_type, t_rep0)
    grid.info["cluster"] = kdet["label"]
    grid.info["cluster_id"] = kdet["cluster_id"]
    static, snames = E.static_features(grid.info, kdet["cluster_id"], kdet["k"])
    fnames = E.feature_names(snames)
    W, dist = E.neighbor_matrix(cfg, grid.info)
    ctx = {"W": W, "ref": grid.info["tier"].eq("A").to_numpy()}
    # Bản riêng cho giai đoạn kiểm định: tier, cụm detector, lân cận chỉ dùng dữ liệu tới 30/04
    kdetV = B.kmeans_detectors(cfg, gridV, day_type, t_val0)
    staticV, _ = E.static_features(gridV.info, kdetV["cluster_id"], kdetV["k"])
    WV, _ = E.neighbor_matrix(cfg, gridV.info)
    ctxV = {"W": WV, "ref": gridV.info["tier"].eq("A").to_numpy()}
    changed = (gridV.info["tier"].to_numpy() != grid.info["tier"].to_numpy()).sum()
    log(f"      tier giai đoạn kiểm định (tới 30/04): {gridV.info['tier'].value_counts().to_dict()}; "
        f"{changed} detector khác tier so với giai đoạn cuối")
    special = set(cfg["calendar"]["special_days"])
    log(f"      ngày lệch lịch: {kd['days'].loc[kd['days'].mismatch, 'day'].tolist()}")
    log(f"      cụm detector (k={kdet['k']}): {kdet['sizes']}")

    log("[3/6] Giai đoạn kiểm định: baseline 01/01–30/04, huấn luyện và chọn mô hình ...")
    baseV = B.build_baseline(gridV, day_type, t_val0, special)
    exV, blkV, XV = _block(cfg, gridV, baseV, day_type, ctxV, staticV, 0, t_rep0)
    YV = E.labels(blkV["E"], cfg["event"]["horizon_windows"])
    okV = ~np.isnan(blkV["z_occ"]) & ~np.isnan(YV)
    t_idx = np.arange(t_rep0)[:, None].repeat(grid.D, 1)
    tr = okV & (t_idx < t_val0 - 2)                     # bỏ 2 khung cuối để nhãn không chạm tháng 5
    va = okV & (t_idx >= t_val0)
    X_tr, y_tr = XV[tr], YV[tr].astype(int)
    X_va, y_va, ev_va = XV[va], YV[va].astype(int), np.nan_to_num(blkV["E"][va])
    rule_v4 = S.priority(np.stack([blkV["C1"], blkV["C2"], blkV["C3"], blkV["C4"],
                                   np.full_like(blkV["C1"], np.nan)], -1), V4_WEIGHTS)
    log(f"      train {len(y_tr):,} dòng (dương {y_tr.mean():.3%}); valid {len(y_va):,} dòng (dương {y_va.mean():.3%})")
    res_val, fitted, dt_scan = M.fit_and_compare(
        X_tr, y_tr, X_va, y_va, ev_va,
        {"persistence": ev_va, "rule_v4": np.nan_to_num(rule_v4[va]) / 100}, rs, cfg["ml"], log=log)
    best = max(["dt", "nb", "mlp", "gb"], key=lambda k: res_val[k]["pr_auc"])
    log(f"      → chọn mô hình: {M.MODEL_LABELS[best]}")

    # C5 trên tập kiểm định → tối ưu trọng số & ngưỡng
    C5V = np.full(blkV["C1"].shape, np.nan, dtype=np.float32)
    okX = ~np.isnan(blkV["z_occ"])
    C5V[okX] = to_c5(fitted[best].predict_proba(XV[okX])[:, 1], cfg)
    sl = slice(t_val0, t_rep0)
    CV = np.stack([blkV[k][sl] for k in ["C1", "C2", "C3", "C4"]] + [C5V[sl]], -1)
    U_va = np.fmax(blkV["E"][sl], YV[sl])            # cần chú ý ngay hoặc trong 30 phút
    sc = cfg["scoring"]
    lo, hi = sc["weight_bounds"]
    log("      tối ưu trọng số (lưới bước 0,05) ...")
    w_best, wgrid, wres = S.optimise_weights(CV, U_va, sc["top_k"], lo, hi, sc["weight_step"])
    score_va = S.priority(CV, w_best)
    curve = S.certainty_curve(score_va, U_va)
    sweep_va = S.threshold_sweep(score_va, U_va, blkV["E"][sl])
    th = S.select_thresholds(sweep_va, sc["threshold_rule"])
    if sc.get("max_high_per_window"):
        th["max_high"] = int(sc["max_high_per_window"])     # năng lực ca trực: tối đa N cảnh báo Cao mỗi khung
    np.savez_compressed(out_dir / "valid_scores.npz", C=CV, score=score_va, U=np.nan_to_num(U_va),
                        event_now=np.nan_to_num(blkV["E"][sl]), Y=np.nan_to_num(YV[sl]))
    active = (np.nan_to_num(U_va) > 0).any(1)
    p10_v4 = S.precision_at_k(S.priority(CV, V4_WEIGHTS), U_va, sc["top_k"], active)
    p10_best = float(wres.max())
    order = np.argsort(-wres)[:10]
    top_w = [{**dict(zip(S.KEYS, [round(float(x), 2) for x in wgrid[i]])), "p_at_10": round(float(wres[i]), 4)}
             for i in order]
    # độ nhạy: thay đổi từng trọng số ±0,05 (bù vào C1) → precision@10
    sens = []
    for k in S.KEYS:
        for dlt in [-0.10, -0.05, 0.05, 0.10]:
            w2 = dict(w_best); w2[k] = round(w2[k] + dlt, 2)
            other = "C1" if k != "C1" else "C5"
            w2[other] = round(w2[other] - dlt, 2)
            if min(w2.values()) < 0:
                continue
            sens.append({"criterion": k, "delta": dlt, "compensate": other,
                         "p_at_10": round(S.precision_at_k(S.priority(CV, w2), U_va, sc["top_k"], active), 4)})
    log(f"      trọng số tối ưu {w_best} (P@10={p10_best:.3f}, v4={p10_v4:.3f}); ngưỡng {th}")
    lvl_va = S.level(score_va, th)
    val_levels = _level_stats(score_va, lvl_va, U_va, blkV["E"][sl])

    log("[4/6] Giai đoạn cuối: baseline 01/01–31/05, huấn luyện lại, chấm tháng 6 ...")
    baseF = B.build_baseline(grid, day_type, t_rep0, special)
    exF, blkF, XF = _block(cfg, grid, baseF, day_type, ctx, static, 0, T)
    YF = E.labels(blkF["E"], cfg["event"]["horizon_windows"])
    okF = ~np.isnan(blkF["z_occ"])
    t_idx = np.arange(T)[:, None].repeat(grid.D, 1)
    trF = okF & ~np.isnan(YF) & (t_idx < t_rep0 - 2)
    params = res_val[best]["params"]
    model = M.make_model(best, rs, **({"max_depth": params["max_depth"]} if best == "dt" else {}))
    ns = cfg["ml"]["mlp_sample"] if best == "mlp" else cfg["ml"]["train_sample"]
    idx = M.sample_rows(int(trF.sum()), ns, rs)
    model.fit(XF[trF][idx], YF[trF][idx].astype(int))
    # cây giải thích (luôn huấn luyện để hiển thị luật, kể cả khi mô hình chính không phải DT)
    dt_depth = res_val["dt"]["params"]["max_depth"]
    explain_tree = M.make_model("dt", rs, max_depth=min(dt_depth, 6)).fit(XF[trF][idx], YF[trF][idx].astype(int))

    P_F = np.full(blkF["C1"].shape, np.nan, dtype=np.float32)
    P_F[okF] = model.predict_proba(XF[okF])[:, 1]
    C5F = to_c5(P_F, cfg)
    te = okF & ~np.isnan(YF) & (t_idx >= t_rep0)
    y_te = YF[te].astype(int)
    ev_te = np.nan_to_num(blkF["E"][te])
    rule_v4F = S.priority(np.stack([blkF["C1"], blkF["C2"], blkF["C3"], blkF["C4"],
                                    np.full_like(blkF["C1"], np.nan)], -1), V4_WEIGHTS)
    res_test = {best: M.evaluate(y_te, P_F[te], ev_te),
                "persistence": M.evaluate(y_te, ev_te, ev_te),
                "rule_v4": M.evaluate(y_te, np.nan_to_num(rule_v4F[te]) / 100, ev_te)}
    log(f"      kiểm thử tháng 6: {M.MODEL_LABELS[best]} PR-AUC={res_test[best]['pr_auc']}, "
        f"persistence={res_test['persistence']['pr_auc']}, rule_v4={res_test['rule_v4']['pr_auc']}")

    sl = slice(t_rep0, T)
    CF = np.stack([blkF[k][sl] for k in ["C1", "C2", "C3", "C4"]] + [C5F[sl]], -1)
    U_te = np.fmax(blkF["E"][sl], YF[sl])
    score_te = S.priority(CF, w_best)
    lvl_te = S.level(score_te, th)
    active_te = (np.nan_to_num(U_te) > 0).any(1)
    score_v4_te = S.priority(CF, V4_WEIGHTS)
    test_levels = _level_stats(score_te, lvl_te, U_te, blkF["E"][sl])
    test_levels_v4 = _level_stats(score_v4_te, S.level(score_v4_te, {"high": 70, "medium": 40}), U_te, blkF["E"][sl])
    p10_te = S.precision_at_k(score_te, U_te, sc["top_k"], active_te)
    p10_te_v4 = S.precision_at_k(score_v4_te, U_te, sc["top_k"], active_te)
    log(f"      P@10 tháng 6: v5={p10_te:.3f} | v4={p10_te_v4:.3f}; mức Cao: {test_levels['dist']['Cao']}%")

    log("[5/6] Phân tích bổ sung (tương quan không gian, tầm quan trọng đặc trưng) ...")
    spatial = _spatial_corr(grid, exF, blkF, t_rep0, dist)
    if hasattr(model, "feature_importances_"):
        imp = model.feature_importances_
    else:
        imp = explain_tree.feature_importances_
    importance = sorted([{"feature": f, "importance": round(float(v), 4)} for f, v in zip(fnames, imp)],
                        key=lambda r: -r["importance"])[:15]
    tree_text = export_text(explain_tree, feature_names=fnames, max_depth=4, decimals=3)

    log("[6/6] Lưu artifacts ...")
    baseF.to_npz(out_dir / "baseline_final.npz")
    joblib.dump(grid, out_dir / "grid.joblib", compress=3)
    np.save(out_dir / "static_features.npy", static)
    joblib.dump({"model": model, "name": best, "features": fnames, "explain_tree": explain_tree},
                out_dir / "model.joblib")
    grid.info.to_csv(out_dir / "detector_info.csv", index=False, encoding="utf-8-sig")
    kd["days"].to_csv(out_dir / "day_clusters.csv", index=False, encoding="utf-8-sig")
    (out_dir / "decision_tree.txt").write_text(tree_text, encoding="utf-8")

    # Kết quả chấm tháng 6 theo lô (đối chiếu với live), dạng dài
    t_abs = np.arange(t_rep0, T)
    lvl_names, tops = lvl_te, S.top_factor(CF, w_best)
    rows = pd.DataFrame({
        "detid": np.tile(np.array(grid.detids), len(t_abs)),
        "day": np.repeat([grid.day_of(t) for t in t_abs], grid.D),
        "slot": np.repeat(t_abs % SLOTS, grid.D),
        "priority_score": score_te.ravel().round(1),
        "priority_level": lvl_names.ravel(),
        "top_factor": tops.ravel(),
        "C1": CF[..., 0].ravel().round(1), "C2": CF[..., 1].ravel().round(1), "C3": CF[..., 2].ravel().round(1),
        "C4": CF[..., 3].ravel().round(1), "C5": CF[..., 4].ravel().round(1),
        "p_event30": P_F[sl].ravel().round(4),
        "z_flow": blkF["z_flow"][sl].ravel().round(2),
        "event_now": blkF["E"][sl].ravel(), "event_next30": YF[sl].ravel(),
    })
    rows.to_parquet(out_dir / "replay_batch.parquet", index=False)

    meta = {
        "built_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "seconds": None,
        "split": {"train": [grid.days[0], cfg["split"]["train_end"]],
                  "valid": [grid.day_of(t_val0), cfg["split"]["valid_end"]],
                  "replay": [cfg["split"]["replay_start"], grid.days[-1]]},
        "profile": profile,
        "kmeans_days": {"scan": kd["scan"], "crosstab": kd["crosstab"].to_dict(),
                        "mismatch": kd["days"].loc[kd["days"].mismatch].to_dict("records"),
                        "centroids": kd["centroids"]},
        "kmeans_detectors": {"scan": kdet["scan"], "k": kdet["k"], "sizes": kdet["sizes"],
                             "centroids": kdet["centroids"], "profiles": kdet["profiles"]},
        "train_rows": int(len(y_tr)), "valid_rows": int(len(y_va)), "test_rows": int(len(y_te)),
        "pos_rate": {"train": round(float(y_tr.mean()), 4), "valid": round(float(y_va.mean()), 4),
                     "test": round(float(y_te.mean()), 4)},
        "models_valid": res_val, "dt_scan": dt_scan, "best_model": best, "best_model_label": M.MODEL_LABELS[best],
        "models_test": res_test, "feature_importance": importance, "features": fnames,
        "weights": w_best, "weights_v4": V4_WEIGHTS, "weights_top": top_w, "sensitivity": sens,
        "thresholds": th, "threshold_rule": sc["threshold_rule"], "threshold_sweep_valid": sweep_va,
        "threshold_sweep_test": S.threshold_sweep(score_te, U_te, blkF["E"][sl]), "certainty_curve": curve, "p_at_10": {"valid_v5": round(p10_best, 4), "valid_v4": round(p10_v4, 4),
                                      "test_v5": round(p10_te, 4), "test_v4": round(p10_te_v4, 4)},
        "levels_valid": val_levels, "levels_test": test_levels, "levels_test_v4": test_levels_v4,
        "spatial_corr": spatial,
        "neighbors_per_detector": {
            "median": float(np.median((W > 0).sum(0))), "min": int((W > 0).sum(0).min()),
            "max": int((W > 0).sum(0).max())},
        "action_mix_test": pd.Series(rows.loc[rows.priority_level == "Cao", "top_factor"]).value_counts(
            normalize=True).round(4).to_dict(),
    }
    meta["seconds"] = round(time.time() - t_start, 1)
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"Xong sau {meta['seconds']} giây → {out_dir}")
    return meta


if __name__ == "__main__":
    run()
