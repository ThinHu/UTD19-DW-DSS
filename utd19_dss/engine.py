"""Lõi tính toán DSS: tiêu chí C1–C4, sự kiện ùn tắc, đặc trưng học máy.

Mọi hàm nhận một khối liên tục các khung [L, D]. Chạy theo lô (batch) thì khối là toàn bộ lưới;
chạy live thì khối là 4 khung gần nhất. Mọi giá trị ở khung t chỉ phụ thuộc dữ liệu ≤ t (C3 dùng
4 khung trước, C4 dùng các detector khác cùng khung, đặc trưng trễ dùng t-1..t-3), nên hai cách
chạy cho cùng kết quả.
"""
from __future__ import annotations

import numpy as np

from .baseline import DAY_TYPES
from .data import SLOTS

LAGS = 3   # số khung trễ dùng trong đặc trưng


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def neighbor_matrix(cfg: dict, info) -> tuple[np.ndarray, np.ndarray]:
    """W[i, j] = trọng số Gaussian của lân cận j đối với i; chỉ lấy lân cận tier A/B."""
    c = cfg["criteria"]["c4"]
    lat = info["lat"].to_numpy(float)
    lon = info["long"].to_numpy(float)
    d = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    W = np.exp(-(d ** 2) / c["sigma_d_km"] ** 2)
    W[(d < c["dmin_km"]) | (d > c["dmax_km"]) | np.isnan(d)] = 0.0
    np.fill_diagonal(W, 0.0)
    src_ok = info["tier"].isin(["A", "B"]).to_numpy()
    W[:, ~src_ok] = 0.0
    return W.T.astype(np.float32), d   # trả về W^T để nhân C1[L, D] @ W^T[D, D]


def city_factor(cfg: dict, x: np.ndarray, mu: np.ndarray, ref: np.ndarray, floor: float) -> np.ndarray:
    """Hệ số mức chung toàn thành phố mỗi khung: trung vị (giá trị / baseline) trên detector tier A."""
    if not cfg["baseline"]["city_norm"]:
        return np.ones(x.shape[0], dtype=np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(ref[None, :] & (mu > floor), x / mu, np.nan)
    cnt = np.sum(~np.isnan(r), axis=1)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            f = np.nanmedian(r, axis=1)
    f = np.where(cnt >= cfg["baseline"]["city_norm_min_ref"], np.clip(f, 0.5, 2.0), 1.0)
    return f.astype(np.float32)


def _rolling_sum_rows(a: np.ndarray, k: int) -> np.ndarray:
    """Tổng trượt k hàng (gồm hàng hiện tại) theo trục 0, bắt đầu từ đầu khối."""
    c = np.cumsum(np.vstack([np.zeros((1, a.shape[1]), a.dtype), a]), axis=0)
    out = c[1:] - c[np.maximum(np.arange(1, a.shape[0] + 1) - k, 0)]
    return out


def compute_block(cfg: dict, occ: np.ndarray, flow: np.ndarray, ex: dict, ctx: dict) -> dict:
    """Tính các đại lượng cho khối [L, D]. ctx chứa W, ref (tier A), các mảng tĩnh."""
    cr, ev = cfg["criteria"], cfg["event"]
    cap = cr["z_cap"]
    f_o = city_factor(cfg, occ, ex["mu_occ"], ctx["ref"], 0.005)
    f_f = city_factor(cfg, flow, ex["mu_flow"], ctx["ref"], 10.0)
    occ_n = occ / f_o[:, None]
    flow_n = flow / f_f[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        z_o = (occ_n - ex["mu_occ"]) / ex["sd_occ"]
        z_f = (flow_n - ex["mu_flow"]) / ex["sd_flow"]
    C1 = np.clip(z_o, 0, cap) / cap * 100
    C2 = np.clip(np.abs(z_f), 0, cap) / cap * 100
    # Sự kiện ùn tắc bất thường (nhãn): z_occ ≥ 2 và occupancy cao hơn kỳ vọng ≥ 5 điểm %
    with np.errstate(invalid="ignore"):
        E = ((z_o >= ev["z_occ"]) & (occ_n - ex["mu_occ"] >= ev["occ_margin"])).astype(np.float32)
    E[np.isnan(z_o)] = np.nan

    # C3: tỷ lệ khung có C1 ≥ ngưỡng trong k khung gần nhất (gồm khung hiện tại), cần ≥ 2 khung hợp lệ
    k = cr["persistence_windows"]
    valid = ~np.isnan(C1)
    hit = (np.nan_to_num(C1) >= cr["persistence_c1_threshold"]) & valid
    n_valid = _rolling_sum_rows(valid.astype(np.float32), k)
    n_hit = _rolling_sum_rows(hit.astype(np.float32), k)
    with np.errstate(invalid="ignore", divide="ignore"):
        C3 = np.where((n_valid >= 2) & valid, 100 * n_hit / n_valid, np.nan)

    # C4: trung bình có trọng số Gaussian của C1 các lân cận (50 m – 1 km)
    W = ctx["W"]
    num = np.nan_to_num(C1) @ W
    den = valid.astype(np.float32) @ W
    with np.errstate(invalid="ignore", divide="ignore"):
        C4 = np.where(den > 0, num / den, np.nan)
    return {"f_occ": f_o, "f_flow": f_f, "occ_n": occ_n, "flow_n": flow_n, "z_occ": z_o, "z_flow": z_f,
            "C1": C1, "C2": C2, "C3": C3, "C4": C4, "E": E}


# ---------------------------------------------------------------------------
# Đặc trưng học máy
# ---------------------------------------------------------------------------
FEATURES = [
    "occ", "occ_minus_mu", "flow_ratio", "z_occ", "z_flow",
    "z_occ_l1", "z_occ_l2", "z_occ_l3", "dz1", "n_lags", "event_now",
    "C3", "C4", "mu_ramp", "city_f_occ", "err_ratio",
    "hour_sin", "hour_cos", "dt_WD", "dt_SAT", "dt_SUN",
    "det_mean_occ", "tier_code", "fc_primary", "fc_secondary", "fc_tertiary", "fc_other",
]


def static_features(info, cluster_id: np.ndarray, n_clusters: int) -> tuple[np.ndarray, list[str]]:
    fc = info["fclass"].fillna("other").to_numpy()
    cols = [
        np.nan_to_num(info["mean_occ"].to_numpy(float)),
        info["tier"].map({"A": 0, "B": 1, "C": 2, "X": 3}).to_numpy(float),
        (fc == "primary") | (fc == "primary_link"),
        fc == "secondary",
        fc == "tertiary",
        ~np.isin(fc, ["primary", "primary_link", "secondary", "tertiary"]),
    ]
    names = ["det_mean_occ", "tier_code", "fc_primary", "fc_secondary", "fc_tertiary", "fc_other"]
    for c in range(n_clusters):
        cols.append(cluster_id == c)
        names.append(f"cl_{c}")
    return np.vstack(cols).T.astype(np.float32), names


def build_features(blk: dict, ex: dict, mu_next2: np.ndarray, occ: np.ndarray, flow: np.ndarray,
                   err_ratio: np.ndarray, t_abs: np.ndarray, day_type_rows: np.ndarray,
                   static: np.ndarray) -> np.ndarray:
    """Ma trận đặc trưng [L, D, F]; hàng có lag lấy từ các hàng trước trong khối."""
    L, D = occ.shape
    z = np.clip(blk["z_occ"], -5, 10)
    zf = np.clip(blk["z_flow"], -5, 10)

    def lag(a, k):
        out = np.full_like(a, np.nan)
        out[k:] = a[:-k]
        return out

    l1, l2, l3 = lag(z, 1), lag(z, 2), lag(z, 3)
    n_lags = (~np.isnan(l1)).astype(np.float32) + (~np.isnan(l2)) + (~np.isnan(l3))
    with np.errstate(invalid="ignore", divide="ignore"):
        flow_ratio = np.clip(blk["flow_n"] / np.maximum(ex["mu_flow"], 1.0), 0, 5)
    slot = t_abs % SLOTS
    ang = 2 * np.pi * (slot + 0.5) / SLOTS
    rowf = np.stack([np.sin(ang), np.cos(ang),
                     day_type_rows == "WD", day_type_rows == "SAT", day_type_rows == "SUN"], 1).astype(np.float32)
    feats = [
        blk["occ_n"], blk["occ_n"] - ex["mu_occ"], flow_ratio, z, zf,
        np.nan_to_num(l1), np.nan_to_num(l2), np.nan_to_num(l3), np.nan_to_num(z - l1), n_lags,
        np.nan_to_num(blk["E"]), np.nan_to_num(blk["C3"]), np.nan_to_num(blk["C4"]),
        np.nan_to_num(mu_next2 - ex["mu_occ"]),
        np.repeat(blk["f_occ"][:, None], D, 1), np.nan_to_num(err_ratio),
    ]
    X = np.stack([np.asarray(a, dtype=np.float32) for a in feats], axis=2)            # [L, D, 16]
    R = np.repeat(rowf[:, None, :], D, axis=1)                                         # [L, D, 5]
    S = np.repeat(static[None, :, :], L, axis=0)                                       # [L, D, s]
    return np.concatenate([X, R, S], axis=2)


def feature_names(static_names: list[str]) -> list[str]:
    return FEATURES[:21] + static_names


def labels(E: np.ndarray, horizon: int) -> np.ndarray:
    """Y_t = 1 nếu có sự kiện ở bất kỳ khung nào trong t+1..t+h; NaN nếu tất cả đều thiếu."""
    L = E.shape[0]
    stack = np.full((horizon, L, E.shape[1]), np.nan, dtype=np.float32)
    for h in range(1, horizon + 1):
        stack[h - 1, :L - h] = E[h:]
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmax(stack, axis=0)


def day_type_rows(day_type: np.ndarray, t_abs: np.ndarray) -> np.ndarray:
    return day_type[t_abs // SLOTS]


__all__ = ["compute_block", "build_features", "labels", "neighbor_matrix", "static_features",
           "feature_names", "DAY_TYPES"]
