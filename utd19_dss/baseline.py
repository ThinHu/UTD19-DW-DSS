"""Loại ngày (K-means) và baseline lịch sử theo loại ngày × khung 15 phút × detector."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .data import SLOTS, Grid

DAY_TYPES = ["WD", "SAT", "SUN"]
DAY_TYPE_LABEL = {"WD": "Ngày làm việc", "SAT": "Thứ Bảy", "SUN": "Chủ nhật / Lễ"}


def calendar_day_type(day: str, holidays: set[str]) -> str:
    dow = pd.Timestamp(day).day_of_week
    if day in holidays or dow == 6:
        return "SUN"
    if dow == 5:
        return "SAT"
    return "WD"


# ---------------------------------------------------------------------------
# K-means phân cụm ngày theo hồ sơ lưu lượng toàn thành phố
# ---------------------------------------------------------------------------
def day_profiles(grid: Grid, t_end: int) -> pd.DataFrame:
    ref = grid.info["tier"].eq("A").to_numpy()
    flow = grid.flow[:t_end, ref]
    n_days = t_end // SLOTS
    prof = np.nanmean(flow.reshape(n_days, SLOTS, -1), axis=2)   # [ngày, 96]
    df = pd.DataFrame(prof, index=grid.days[:n_days])
    return df.fillna(df.mean())


def kmeans_day_types(cfg: dict, grid: Grid, t_end: int) -> dict:
    prof = day_profiles(grid, t_end)
    X = prof.to_numpy() / np.nanmean(prof.to_numpy())
    rs = cfg["kmeans"]["random_state"]
    scan = []
    for k in range(2, 7):
        km = KMeans(k, n_init=20, random_state=rs).fit(X)
        scan.append({"k": k, "inertia": round(float(km.inertia_), 2),
                     "silhouette": round(float(silhouette_score(X, km.labels_)), 3)})
    k = cfg["kmeans"]["day_k"]
    km = KMeans(k, n_init=20, random_state=rs).fit(X)
    days = prof.index.tolist()
    dow = pd.to_datetime(pd.Series(days)).dt.day_of_week.to_numpy()
    lab = km.labels_
    # Đặt tên cụm theo thứ chiếm đa số: Chủ nhật → SUN, Thứ Bảy → SAT, còn lại WD
    names = {}
    for c in range(k):
        sun = np.mean(dow[lab == c] == 6)
        sat = np.mean(dow[lab == c] == 5)
        names[c] = "SUN" if sun >= 0.5 else ("SAT" if sat >= 0.5 else "WD")
    holidays = set(cfg["calendar"]["holidays"])
    rows = []
    for d, l, w in zip(days, lab, dow):
        rows.append({"day": d, "dow": int(w), "cluster": names[int(l)],
                     "calendar": calendar_day_type(d, holidays),
                     "level": round(float(prof.loc[d].mean()), 1)})
    tab = pd.DataFrame(rows)
    tab["mismatch"] = tab["cluster"] != tab["calendar"]
    centroids = {names[c]: (km.cluster_centers_[c] * np.nanmean(prof.to_numpy())).round(1).tolist() for c in range(k)}
    cross = pd.crosstab(tab["dow"], tab["cluster"]).reindex(columns=DAY_TYPES, fill_value=0)
    return {"scan": scan, "days": tab, "centroids": centroids, "crosstab": cross}


# ---------------------------------------------------------------------------
# K-means phân cụm detector theo hình dạng hồ sơ occupancy ngày làm việc
# ---------------------------------------------------------------------------
def kmeans_detectors(cfg: dict, grid: Grid, day_type: np.ndarray, t_end: int) -> dict:
    """Phân cụm detector theo hồ sơ occupancy 24 giờ của ngày làm việc (chuẩn hóa z theo từng detector)."""
    rs = cfg["kmeans"]["random_state"]
    n_days = t_end // SLOTS
    wd = np.repeat(day_type[:n_days] == "WD", SLOTS)
    occ = grid.occ[:t_end][wd]
    prof = np.nanmean(occ.reshape(-1, SLOTS, grid.D), axis=0).T      # [D, 96]
    hourly = prof.reshape(grid.D, 24, 4).mean(2)                        # [D, 24]
    ok = ~np.isnan(hourly).any(1) & (np.nanmean(hourly, 1) > 0)
    h = hourly[ok]
    X = (h - h.mean(1, keepdims=True)) / np.maximum(h.std(1, keepdims=True), 1e-9)
    scan = []
    for k in range(cfg["kmeans"]["detector_k_range"][0], cfg["kmeans"]["detector_k_range"][1] + 1):
        km = KMeans(k, n_init=20, random_state=rs).fit(X)
        scan.append({"k": k, "inertia": round(float(km.inertia_), 2),
                     "silhouette": round(float(silhouette_score(X, km.labels_)), 3),
                     "sizes": sorted(np.bincount(km.labels_).tolist(), reverse=True)})
    k = cfg["kmeans"]["detector_k"]
    km = KMeans(k, n_init=20, random_state=rs).fit(X)
    used = {}
    for c in range(k):
        cen = km.cluster_centers_[c]
        lvl = float(h[km.labels_ == c].mean())
        am, pm = cen[6:10].max(), cen[15:19].max()
        if lvl < 0.01:
            nm = "Tải rất thấp"
        elif am > pm + 0.5:
            nm = "Đỉnh buổi sáng"
        elif pm > am + 0.5:
            nm = "Đỉnh buổi chiều"
        else:
            nm = "Hai đỉnh sáng–chiều"
        if nm in used.values():
            nm = f"{nm} {c + 1}"
        used[c] = nm
    label = np.full(grid.D, "Chưa phân cụm", dtype=object)
    label[np.where(ok)[0]] = [used[int(l)] for l in km.labels_]
    cid = np.full(grid.D, -1)
    cid[np.where(ok)[0]] = km.labels_
    centroids = {used[c]: km.cluster_centers_[c].round(3).tolist() for c in range(k)}
    profiles = {used[c]: h[km.labels_ == c].mean(0).round(4).tolist() for c in range(k)}
    sizes = {used[c]: int((km.labels_ == c).sum()) for c in range(k)}
    return {"scan": scan, "k": k, "label": label, "cluster_id": cid, "centroids": centroids,
            "profiles": profiles, "sizes": sizes}


# ---------------------------------------------------------------------------
# Baseline: tổng, tổng bình phương, số mẫu theo (loại ngày, khung, detector)
# ---------------------------------------------------------------------------
@dataclass
class Baseline:
    n_o: np.ndarray; s_o: np.ndarray; ss_o: np.ndarray   # [3, 96, D]
    n_f: np.ndarray; s_f: np.ndarray; ss_f: np.ndarray
    t_end: int                                           # baseline dựng từ các khung t < t_end
    include: np.ndarray                                  # [t_end] khung nào được đưa vào baseline

    def to_npz(self, path):
        np.savez_compressed(path, n_o=self.n_o, s_o=self.s_o, ss_o=self.ss_o, n_f=self.n_f, s_f=self.s_f,
                            ss_f=self.ss_f, t_end=self.t_end, include=self.include)

    @classmethod
    def from_npz(cls, path):
        z = np.load(path)
        return cls(z["n_o"], z["s_o"], z["ss_o"], z["n_f"], z["s_f"], z["ss_f"], int(z["t_end"]), z["include"])


def build_baseline(grid: Grid, day_type: np.ndarray, t_end: int, exclude_days: set[str]) -> Baseline:
    D = grid.D
    g_ix = {g: i for i, g in enumerate(DAY_TYPES)}
    out = {k: np.zeros((3, SLOTS, D), dtype=np.float64) for k in ["n_o", "s_o", "ss_o", "n_f", "s_f", "ss_f"]}
    include = np.zeros(t_end, dtype=bool)
    for di in range(t_end // SLOTS):
        day = grid.days[di]
        if day in exclude_days:
            continue
        g = g_ix[day_type[di]]
        sl = slice(di * SLOTS, (di + 1) * SLOTS)
        include[sl] = True
        o, f = grid.occ[sl].astype(np.float64), grid.flow[sl].astype(np.float64)
        ok = ~np.isnan(o) & ~np.isnan(f)
        out["n_o"][g] += ok
        out["s_o"][g] += np.where(ok, o, 0)
        out["ss_o"][g] += np.where(ok, o * o, 0)
        out["n_f"][g] += ok
        out["s_f"][g] += np.where(ok, f, 0)
        out["ss_f"][g] += np.where(ok, f * f, 0)
    return Baseline(**out, t_end=t_end, include=include)


def expected(cfg: dict, base: Baseline, grid: Grid, day_type: np.ndarray, t0: int, t1: int,
             occ: np.ndarray | None = None, flow: np.ndarray | None = None) -> dict:
    """mu/sd cho các khung t0..t1-1. Khung nằm trong baseline thì bỏ chính nó (leave-one-out)."""
    bc = cfg["baseline"]
    occ = grid.occ[t0:t1] if occ is None else occ
    flow = grid.flow[t0:t1] if flow is None else flow
    t = np.arange(t0, t1)
    g = np.array([DAY_TYPES.index(x) for x in day_type[t // SLOTS]])
    s = t % SLOTS
    n_o, s_o, ss_o = base.n_o[g, s], base.s_o[g, s], base.ss_o[g, s]
    n_f, s_f, ss_f = base.n_f[g, s], base.s_f[g, s], base.ss_f[g, s]
    loo = np.zeros(len(t), dtype=bool)
    inside = t < base.t_end
    loo[inside] = base.include[t[inside]]
    loo = loo[:, None] & ~np.isnan(occ) & ~np.isnan(flow)
    o0, f0 = np.nan_to_num(occ), np.nan_to_num(flow)
    n_o = n_o - loo; s_o = s_o - loo * o0; ss_o = ss_o - loo * o0 * o0
    n_f = n_f - loo; s_f = s_f - loo * f0; ss_f = ss_f - loo * f0 * f0
    with np.errstate(invalid="ignore", divide="ignore"):
        mu_o = s_o / n_o
        mu_f = s_f / n_f
        sd_o = np.sqrt(np.clip((ss_o - n_o * mu_o ** 2) / (n_o - 1), 0, None))
        sd_f = np.sqrt(np.clip((ss_f - n_f * mu_f ** 2) / (n_f - 1), 0, None))
    enough = n_o >= bc["min_n"]
    mu_o = np.where(enough, mu_o, np.nan); mu_f = np.where(enough, mu_f, np.nan)
    sd_o = np.where(enough, np.maximum(sd_o, np.maximum(bc["sigma_floor_occ"], bc["sigma_floor_rel"] * mu_o)), np.nan)
    sd_f = np.where(enough, np.maximum(sd_f, np.maximum(bc["sigma_floor_flow"], bc["sigma_floor_rel"] * mu_f)), np.nan)
    return {"mu_occ": mu_o.astype(np.float32), "sd_occ": sd_o.astype(np.float32),
            "mu_flow": mu_f.astype(np.float32), "sd_flow": sd_f.astype(np.float32), "n": n_o}


def expected_plain(cfg: dict, base: Baseline, day_type_of_day: str, D: int) -> dict:
    """mu/sd (không LOO) cho cả 96 khung của một loại ngày — dùng cho biểu đồ 'kỳ vọng'."""
    g = DAY_TYPES.index(day_type_of_day)
    bc = cfg["baseline"]
    with np.errstate(invalid="ignore", divide="ignore"):
        mu_o = base.s_o[g] / base.n_o[g]
        mu_f = base.s_f[g] / base.n_f[g]
        sd_o = np.sqrt(np.clip((base.ss_o[g] - base.n_o[g] * mu_o ** 2) / (base.n_o[g] - 1), 0, None))
        sd_f = np.sqrt(np.clip((base.ss_f[g] - base.n_f[g] * mu_f ** 2) / (base.n_f[g] - 1), 0, None))
    ok = base.n_o[g] >= bc["min_n"]
    return {"mu_occ": np.where(ok, mu_o, np.nan), "mu_flow": np.where(ok, mu_f, np.nan),
            "sd_occ": np.where(ok, sd_o, np.nan), "sd_flow": np.where(ok, sd_f, np.nan)}
