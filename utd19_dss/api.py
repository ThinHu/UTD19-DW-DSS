"""REST API cho dashboard DSS.

    uvicorn utd19_dss.api:app --port 8000        # hoặc: make dss-api
    Mở http://localhost:8000
"""
from __future__ import annotations

import asyncio
import io
import json
import math
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import baseline as B
from . import scoring as S
from .config import BASE_DIR, artifacts_dir
from .data import SLOTS
from .live import LiveEngine, slot_label
from .dwinfo import DwInfo

ENG: LiveEngine | None = None
DW: DwInfo | None = None
FRONTEND = BASE_DIR / "frontend" / "dist"


def clean(o):
    """Đổi NaN/Inf/numpy sang kiểu JSON hợp lệ."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def records(df: pd.DataFrame) -> list[dict]:
    return clean(df.to_dict("records"))


async def replay_loop():
    while True:
        await asyncio.sleep(ENG.tick_seconds if ENG else 1)
        if ENG and ENG.playing:
            if ENG.next_t >= ENG.T:
                ENG.playing = False
            else:
                ENG.advance(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ENG, DW
    ENG = LiveEngine()
    DW = DwInfo(ENG.cfg)
    ENG.weights = {k: round(v, 2) for k, v in ENG.weights.items()}
    task = asyncio.create_task(replay_loop())
    yield
    task.cancel()


app = FastAPI(title="DSS Ưu tiên điều phối giao thông Luzern", version="5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _t(day: str | None, slot: int | None) -> int:
    if day is None or slot is None:
        return ENG.now_t
    try:
        t = ENG.grid.t_index(day, int(slot))
    except ValueError:
        raise HTTPException(404, "Không có khung này")
    if t < ENG.t_rep0 or t > ENG.now_t:
        raise HTTPException(400, "Khung chưa được phát lại hoặc nằm ngoài giai đoạn live")
    return t


def _level_counts(lvl) -> dict:
    s = pd.Series(lvl).value_counts()
    return {L: int(s.get(L, 0)) for L in S.LEVELS}


# ---------------------------------------------------------------------------
# Thông tin chung
# ---------------------------------------------------------------------------
@app.get("/api/meta")
def meta():
    m = ENG.meta
    info = ENG.info
    dets = info[["detid", "road", "fclass", "lat", "long", "tier", "error_pct", "cluster", "x_reason",
                 "usable_ratio", "mean_occ", "mean_flow", "last_seen"]]
    replay_days = ENG.grid.days[ENG.t_rep0 // SLOTS:]
    return clean({
        "city": "Luzern", "country": "Thụy Sĩ", "data_range": [ENG.grid.days[0], ENG.grid.days[-1]],
        "split": m["split"], "replay_days": replay_days,
        "day_types": {d: B.DAY_TYPE_LABEL[ENG.day_type[ENG.grid.day_index(d)]] for d in replay_days},
        "detectors": records(dets), "weights": ENG.weights, "weights_default": m["weights"],
        "weights_v4": m["weights_v4"], "thresholds": ENG.thresholds,
        "certainty_curve": m.get("certainty_curve"), "factor_labels": S.FACTOR_LABELS,
        "model": {"name": m["best_model"], "label": m["best_model_label"]},
        "clusters": m["kmeans_detectors"]["sizes"], "tick_seconds": ENG.tick_seconds,
        "fclasses": sorted(info["fclass"].dropna().unique().tolist()),
        "built_at": m["built_at"],
    })


@app.get("/api/state")
def state():
    sc, lvl, _ = ENG.score_matrix()
    counts = _level_counts(lvl)
    prev = None
    if ENG.now_t > ENG.t_rep0:
        _, lvl0, _ = ENG.score_matrix(t=ENG.now_t - 1)
        prev = _level_counts(lvl0)
    # thay đổi so với cùng giờ hôm trước (nếu có)
    yday = None
    if ENG.now_t - SLOTS >= ENG.t_rep0:
        _, lvl1, _ = ENG.score_matrix(t=ENG.now_t - SLOTS)
        yday = _level_counts(lvl1)
    active = int((ENG.tier != "X").sum())
    live = int((~np.isnan(ENG.grid.occ[ENG.now_t])).sum())
    return clean({"now": ENG.now(), "playing": ENG.playing, "tick_seconds": ENG.tick_seconds,
                  "source": ENG.source, "counts": counts, "counts_prev": prev, "counts_yesterday": yday,
                  "detectors_total": ENG.D, "detectors_active": active, "detectors_reporting": live,
                  "weights": ENG.weights, "thresholds": ENG.thresholds})


# ---------------------------------------------------------------------------
# Điều khiển phát lại
# ---------------------------------------------------------------------------
class ReplayCmd(BaseModel):
    action: str                       # play | pause | step | seek | reset | speed
    n: int | None = 1
    day: str | None = None
    slot: int | None = None
    tick_seconds: float | None = None


@app.post("/api/replay")
def replay(cmd: ReplayCmd):
    a = cmd.action
    if a == "play":
        ENG.playing = True
    elif a == "pause":
        ENG.playing = False
    elif a == "step":
        ENG.advance(max(1, min(int(cmd.n or 1), 96 * 31)))
    elif a == "seek":
        try:
            ENG.seek(cmd.day, int(cmd.slot))
        except ValueError as e:
            raise HTTPException(400, str(e))
    elif a == "reset":
        ENG.playing = False
        ENG.reset()
    elif a == "speed":
        ENG.tick_seconds = max(0.5, float(cmd.tick_seconds or 3))
    else:
        raise HTTPException(400, "action không hợp lệ")
    return state()


# ---------------------------------------------------------------------------
# Xếp hạng theo khung
# ---------------------------------------------------------------------------
def _filtered(df, fclass, tier, level, q, cluster):
    if fclass:
        df = df[df["fclass"].isin(fclass.split(","))]
    if tier:
        df = df[df["tier"].isin(tier.split(","))]
    if level:
        df = df[df["level"].isin(level.split(","))]
    if cluster:
        df = df[df["cluster"] == cluster]
    if q:
        ql = q.lower()
        df = df[df["detid"].str.lower().str.contains(ql) | df["road"].str.lower().str.contains(ql)]
    return df


@app.get("/api/window")
def window(day: str | None = None, slot: int | None = None, fclass: str | None = None, tier: str | None = None,
           level: str | None = None, q: str | None = None, cluster: str | None = None, limit: int = 500):
    t = _t(day, slot)
    df = ENG.window_table(t)
    f = _filtered(df, fclass, tier, level, q, cluster)
    return clean({"day": ENG.grid.day_of(t), "slot": t % SLOTS, "label": slot_label(t % SLOTS),
                  "counts": _level_counts(f["level"]), "total": int(len(f)), "rows": records(f.head(limit))})


@app.get("/api/window.csv")
def window_csv(day: str | None = None, slot: int | None = None, fclass: str | None = None,
               tier: str | None = None, level: str | None = None, q: str | None = None):
    t = _t(day, slot)
    df = _filtered(ENG.window_table(t), fclass, tier, level, q, None)
    buf = io.StringIO()
    df.drop(columns=["rank"]).to_csv(buf, index=False)
    name = f"dss_priority_{ENG.grid.day_of(t)}_{slot_label(t % SLOTS).replace(':', '')}.csv"
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/timeline")
def timeline(day: str | None = None):
    """Số detector mức Cao / Trung bình theo từng khung của một ngày (đã phát lại)."""
    day = day or ENG.grid.day_of(ENG.now_t)
    t0 = ENG.grid.t_index(day, 0)
    out = []
    for s in range(SLOTS):
        t = t0 + s
        if t < ENG.t_rep0 or t > ENG.now_t:
            out.append({"slot": s, "label": slot_label(s), "high": None, "medium": None})
            continue
        _, lvl, _ = ENG.score_matrix(t=t)
        c = _level_counts(lvl)
        out.append({"slot": s, "label": slot_label(s), "high": c["Cao"], "medium": c["Trung bình"]})
    return {"day": day, "slots": out}


# ---------------------------------------------------------------------------
# Chi tiết detector
# ---------------------------------------------------------------------------
@app.get("/api/detector/{detid}")
def detector(detid: str, day: str | None = None, slot: int | None = None):
    if detid not in ENG.grid.detids:
        raise HTTPException(404, "Không có detector")
    t = _t(day, slot)
    i = ENG.grid.detids.index(detid)
    d = ENG.grid.day_of(t)
    t0 = ENG.grid.t_index(d, 0)
    dt = ENG.day_type[ENG.grid.day_index(d)]
    exp = B.expected_plain(ENG.cfg, ENG.base, dt, ENG.D)
    series = []
    for s in range(SLOTS):
        tt = t0 + s
        r = tt - ENG.t_rep0
        known = ENG.t_rep0 <= tt <= ENG.now_t
        sc = lvl = None
        if known:
            scw, lvw, _ = ENG.score_matrix(t=tt)        # mức tính trên cả khung (giới hạn năng lực theo khung)
            scv = scw[i]
            sc = None if np.isnan(scv) else round(float(scv), 1)
            lvl = lvw[i]
        series.append({
            "slot": s, "label": slot_label(s),
            "occ": float(ENG.grid.occ[tt, i]) if known else None,
            "flow": float(ENG.grid.flow[tt, i]) if known else None,
            "mu_occ": exp["mu_occ"][s, i], "sd_occ": exp["sd_occ"][s, i],
            "mu_flow": exp["mu_flow"][s, i], "sd_flow": exp["sd_flow"][s, i],
            "score": sc, "level": lvl, "p_event30": float(ENG.P[r, i]) if known else None,
        })
    row = ENG.window_table(t)
    row = row[row["detid"] == detid].iloc[0].to_dict()
    nb_w = ENG.ctx["W"][:, i]
    nb_idx = np.argsort(-nb_w)[:6]
    sc_now, lvl_now, _ = ENG.score_matrix(t=t)
    neighbors = [{"detid": ENG.grid.detids[j], "road": ENG.info["road"].iat[j],
                  "distance_m": round(float(ENG.dist[i, j]) * 1000), "weight": round(float(nb_w[j]), 3),
                  "score": sc_now[j], "level": lvl_now[j]} for j in nb_idx if nb_w[j] > 0]
    inf = ENG.info.iloc[i].to_dict()
    weights = ENG.weights
    contrib = {k: (None if row[k] is None or (isinstance(row[k], float) and math.isnan(row[k]))
                   else round(float(row[k]) * weights[k], 1)) for k in S.KEYS}
    return clean({"detid": detid, "info": inf, "day": d, "day_type": B.DAY_TYPE_LABEL[dt], "slot": t % SLOTS,
                  "label": slot_label(t % SLOTS), "now": row, "contrib": contrib, "series": series,
                  "neighbors": neighbors, "explain": ENG.explain(detid, t),
                  "cluster_profile": ENG.meta["kmeans_detectors"]["profiles"].get(inf.get("cluster"), None)})


# ---------------------------------------------------------------------------
# What-if: thay trọng số / ngưỡng và xem xếp hạng thay đổi
# ---------------------------------------------------------------------------
class WhatIf(BaseModel):
    weights: dict[str, float]
    thresholds: dict[str, float] | None = None
    apply: bool = False


@app.post("/api/whatif")
def whatif(req: WhatIf):
    w = {k: max(0.0, float(req.weights.get(k, 0))) for k in S.KEYS}
    tot = sum(w.values())
    if tot <= 0:
        raise HTTPException(400, "Tổng trọng số phải > 0")
    w = {k: v / tot for k, v in w.items()}
    th = {**ENG.thresholds, **(req.thresholds or {})}      # giữ max_high nếu yêu cầu không gửi
    base = ENG.window_table()
    new = ENG.window_table(weights=w, thresholds=th)
    k = 10
    top_old = base.head(k)["detid"].tolist()
    top_new = new.head(k)["detid"].tolist()
    # chỉ số đánh giá trên các khung đã phát lại (dùng nhãn thực tế đã biết)
    hist = _eval_live(w, th)
    if req.apply:
        ENG.weights, ENG.thresholds = {kk: round(v, 3) for kk, v in w.items()}, dict(th)
    old_rank = {d: r + 1 for r, d in enumerate(base["detid"])}
    rows = new.head(15).copy()
    rows["old_rank"] = rows["detid"].map(old_rank)
    return clean({"weights": w, "thresholds": th, "counts": _level_counts(new["level"]),
                  "counts_current": _level_counts(base["level"]),
                  "overlap_top10": len(set(top_old) & set(top_new)), "rows": records(rows),
                  "eval": hist, "eval_current": _eval_live(ENG.weights, ENG.thresholds), "applied": req.apply})


def _eval_live(weights, thresholds) -> dict:
    """Đánh giá trên các khung đã phát lại mà nhãn 30 phút đã biết (giai đoạn Evaluation)."""
    end = ENG.now_t - 2 - ENG.t_rep0               # nhãn của khung t cần t+1, t+2 đã tới
    if end <= 0:
        return {"windows": 0}
    C = ENG.C[:end]
    sc = S.priority(C, weights)
    lvl = S.level(sc, thresholds)
    ev = ENG.event[:end + 2]
    y = np.fmax(ev[1:end + 1], ev[2:end + 2])
    U = np.fmax(ev[:end], y)
    act = (np.nan_to_num(U) > 0).any(1)
    out = {"windows": int(end)}
    if act.any():
        out["p_at_10"] = round(S.precision_at_k(sc, U, 10, act), 4)
    hi = lvl == "Cao"
    out["high_alerts"] = int(hi.sum())
    out["high_precision"] = round(float(np.nan_to_num(U)[hi].mean()), 4) if hi.any() else None
    ev_all = np.nan_to_num(U) > 0
    out["events"] = int(ev_all.sum())
    out["event_recall_high"] = round(float((hi & ev_all).sum() / max(ev_all.sum(), 1)), 4)
    out["high_per_window"] = round(float(hi.sum(1).mean()), 2)
    return out


# ---------------------------------------------------------------------------
# Goal seeking: cho mục tiêu kết quả → tìm ngưỡng mức Cao (biến quyết định)
# ---------------------------------------------------------------------------
_VALID: dict | None = None


def _valid_set() -> dict:
    """Tiêu chí C1–C5 và nhãn của tháng 5 (tập kiểm định) do build lưu trong valid_scores.npz."""
    global _VALID
    if _VALID is None:
        z = np.load(artifacts_dir(ENG.cfg) / "valid_scores.npz")
        _VALID = {"C": z["C"], "U": z["U"]}
    return _VALID


def _live_target(end: int):
    ev = ENG.event[:end + 2]
    return np.fmax(ev[:end], np.fmax(ev[1:end + 1], ev[2:end + 2]))


class GoalSeek(BaseModel):
    goal: str                         # precision | recall | alerts
    value: float
    weights: dict[str, float] | None = None
    apply: bool = False


@app.post("/api/goalseek")
def goalseek(req: GoalSeek):
    if req.goal not in S.GOALS:
        raise HTTPException(400, "Mục tiêu không hợp lệ")
    w = req.weights or ENG.weights
    tot = sum(max(0.0, float(w.get(k, 0))) for k in S.KEYS)
    if tot <= 0:
        raise HTTPException(400, "Tổng trọng số phải > 0")
    w = {k: max(0.0, float(w.get(k, 0))) / tot for k in S.KEYS}
    V = _valid_set()
    curve = S.threshold_curve(S.priority(V["C"], w), V["U"])
    pick = S.goal_seek(curve, req.goal, req.value)
    live = None
    end = ENG.now_t - 2 - ENG.t_rep0
    if pick and end > 8:
        lc = S.threshold_curve(S.priority(ENG.C[:end], w), _live_target(end))
        live = next(r for r in lc if r["threshold"] == pick["threshold"])
        live["windows"] = int(end)
    current = next((r for r in curve if r["threshold"] == int(round(ENG.thresholds["high"]))), None)
    applied = False
    if req.apply and pick:
        th = int(pick["threshold"])
        ENG.thresholds = {**ENG.thresholds, "high": th, "medium": min(int(ENG.thresholds["medium"]), th - 5)}
        applied = True
    return clean({"goal": req.goal, "goal_label": S.GOALS[req.goal][0], "value": req.value, "weights": w,
                  "pick": pick, "feasible": pick is not None, "live": live, "current": current,
                  "thresholds": ENG.thresholds, "applied": applied, "curve": curve})


# ---------------------------------------------------------------------------
# Kho dữ liệu: nhật ký ETL, đối soát, cách ly, siêu dữ liệu (chỉ đọc)
# ---------------------------------------------------------------------------
@app.get("/api/dw/quality")
def dw_quality():
    if not DW or not DW.available:
        raise HTTPException(503, "Chưa có kho dữ liệu data/work/utd19.duckdb — chạy: python -m utd19_dw.pipeline")
    return clean(DW.quality())


# ---------------------------------------------------------------------------
# Nhật ký hành động (Implementation) và đánh giá kết quả (Evaluation)
# ---------------------------------------------------------------------------
class ActionReq(BaseModel):
    detid: str
    decision: str = "Chấp nhận"          # Chấp nhận | Điều chỉnh | Bỏ qua
    action_code: str | None = None
    action_text: str | None = None
    note: str | None = ""
    operator: str | None = "AN"


@app.post("/api/actions")
def add_action(req: ActionReq):
    df = ENG.window_table()
    row = df[df["detid"] == req.detid]
    if row.empty:
        raise HTTPException(404, "Không có detector")
    r = row.iloc[0]
    t = ENG.now_t
    ws = pd.Timestamp(ENG.grid.day_of(t)) + pd.Timedelta(minutes=15 * (t % SLOTS))
    rid = ENG.store.add_action({
        "window_start": ws, "detid": req.detid, "road": r["road"],
        "priority_score": None if pd.isna(r["score"]) else float(r["score"]), "priority_level": r["level"],
        "action_code": req.action_code or r["action_code"], "action_text": req.action_text or r["action"],
        "decision": req.decision, "note": req.note, "operator": req.operator})
    return {"id": rid}


@app.get("/api/actions")
def list_actions():
    df = ENG.store.actions()
    out = []
    for rec in records(df):
        ws = pd.Timestamp(rec["window_start"])
        t = ENG.grid.t_index(ws.strftime("%Y-%m-%d"), ws.hour * 4 + ws.minute // 15)
        i = ENG.grid.detids.index(rec["detid"])
        r = t - ENG.t_rep0
        outcome = "Chờ dữ liệu"
        if 0 <= r and t + 2 <= ENG.now_t:
            nxt = ENG.event[r + 1:r + 3, i]
            if np.isnan(nxt).all():
                outcome = "Không đủ dữ liệu"
            else:
                outcome = "Có sự kiện trong 30 phút" if np.nanmax(nxt) > 0 else "Không xảy ra sự kiện"
        rec["outcome"] = outcome
        rec["window_label"] = ws.strftime("%d/%m %H:%M")
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Mô hình & phân tích
# ---------------------------------------------------------------------------
@app.get("/api/model")
def model():
    m = ENG.meta
    keep = ["split", "profile", "kmeans_days", "kmeans_detectors", "train_rows", "valid_rows", "test_rows",
            "pos_rate", "certainty_curve", "threshold_sweep_valid", "threshold_sweep_test", "threshold_rule", "models_valid", "models_test", "dt_scan", "best_model", "best_model_label",
            "feature_importance", "weights", "weights_v4", "weights_top", "sensitivity", "thresholds",
            "p_at_10", "levels_valid", "levels_test", "levels_test_v4", "spatial_corr", "neighbors_per_detector"]
    out = {k: m.get(k) for k in keep}
    out["decision_table"] = [{**r, "action": S.ACTION_CODES[r["code"]]} for r in S.DECISION_TABLE]
    out["live_eval"] = _eval_live(ENG.weights, ENG.thresholds)
    out["live_eval_v4"] = _eval_live(m["weights_v4"], {"high": 70, "medium": 40})
    tree_path = artifacts_dir(ENG.cfg) / "decision_tree.txt"
    out["tree_text"] = tree_path.read_text(encoding="utf-8") if tree_path.exists() else ""
    return clean(out)


@app.get("/api/day_clusters")
def day_clusters():
    p = artifacts_dir(ENG.cfg) / "day_clusters.csv"
    return records(pd.read_csv(p))


# ---------------------------------------------------------------------------
# Nạp dữ liệu thật từ bên ngoài (một khung 15 phút dạng CSV)
# ---------------------------------------------------------------------------
@app.post("/api/ingest", response_class=PlainTextResponse)
async def ingest(request: Request):
    """Thân request là CSV của đúng một khung 15 phút (các cột như mart.dss_detector_window)."""
    body = await request.body()
    try:
        df = pd.read_csv(io.BytesIO(body))
        res = ENG.ingest(df)
    except Exception as e:
        raise HTTPException(400, str(e))
    return json.dumps(res, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Frontend tĩnh
# ---------------------------------------------------------------------------
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = FRONTEND / path
        if path and f.exists() and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND / "index.html")
