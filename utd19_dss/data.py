"""Nạp dữ liệu từ Data Warehouse (hoặc bản xuất CSV) và dựng lưới thời gian × detector.

Đơn vị dữ liệu: 1 detector × 1 khung 15 phút (gộp từ 5 khoảng đo 3 phút của UTD19 Luzern).
Lưới (Grid) lưu occupancy/flow dạng mảng [T, D] với T = số ngày × 96 khung, D = số detector.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import resolve

SLOTS = 96
WINDOW_COLS = ["detid", "day", "slot", "n", "n_err", "n_occ", "n_flow", "n_occ_clean", "n_flow_clean",
               "mean_occ_all", "mean_flow_all", "mean_occ_clean", "mean_flow_clean"]


# ---------------------------------------------------------------------------
# Đọc nguồn
# ---------------------------------------------------------------------------
def load_windows(cfg: dict) -> tuple[pd.DataFrame, str]:
    """Trả về (bảng khung 15 phút, mô tả nguồn). Ưu tiên mart của DW."""
    src = cfg["source"]
    db_path = resolve(cfg, src["dw_db"])
    if db_path.exists():
        try:
            import duckdb
            con = duckdb.connect(str(db_path), read_only=True)
            df = con.execute(f"SELECT * FROM {src['dw_table']}").df()
            con.close()
            if len(df):
                return _normalize(df), f"DuckDB {db_path.name}:{src['dw_table']}"
        except Exception as exc:  # bảng mart chưa được dựng → dùng CSV
            print(f"[data] Không đọc được {src['dw_table']} từ DW ({exc}); dùng CSV.")
    path = resolve(cfg, src["windows_csv"])
    df = pd.read_csv(path, compression="infer")
    return _normalize(df), f"CSV {path.name}"


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    miss = [c for c in WINDOW_COLS if c not in df.columns]
    if miss:
        raise ValueError(f"Bảng khung 15 phút thiếu cột: {miss}")
    df = df[WINDOW_COLS].copy()
    df["detid"] = df["detid"].astype(str).str.strip()
    df["day"] = pd.to_datetime(df["day"]).dt.strftime("%Y-%m-%d")
    df["slot"] = df["slot"].astype(int)
    return df


def load_detectors(cfg: dict) -> pd.DataFrame:
    """Thuộc tính detector: ưu tiên chiều dw.dim_detector của DW, không có thì đọc hồ sơ CSV."""
    det = None
    db_path = resolve(cfg, cfg["source"]["dw_db"])
    if db_path.exists():
        try:
            import duckdb
            con = duckdb.connect(str(db_path), read_only=True)
            det = con.execute("""
                SELECT d.detid, d."long", d.lat, d.road, rc.fclass, d.link_key AS linkid,
                       d.distance_to_downstream_signal_km AS pos, d.speed_limit_kmh AS "limit"
                FROM dw.dim_detector d JOIN dw.dim_road_class rc USING (road_class_key)
                WHERE d.detector_key > 0 AND d.is_current""").df()
            con.close()
            det["fclass"] = det["fclass"].replace({"unknown": None})
        except Exception as exc:
            print(f"[data] Không đọc được dw.dim_detector ({exc}); dùng CSV.")
            det = None
    if det is None or det.empty:
        det = pd.read_csv(resolve(cfg, cfg["source"]["detectors_csv"]), encoding="utf-8-sig")
    det.columns = [c.strip().lower() for c in det.columns]
    det["detid"] = det["detid"].astype(str).str.strip()
    keep = [c for c in ["detid", "long", "lat", "road", "fclass", "linkid", "pos", "limit"] if c in det.columns]
    det = det[keep].copy()
    det["road"] = det["road"].fillna("(không tên)")
    return det


# ---------------------------------------------------------------------------
# Lưới
# ---------------------------------------------------------------------------
@dataclass
class Grid:
    detids: list[str]
    days: list[str]
    occ: np.ndarray            # [T, D] giá trị đã chọn theo tier, NaN nếu không hợp lệ
    flow: np.ndarray
    err_ratio: np.ndarray      # [T, D] tỷ lệ khoảng đo bị gắn error trong khung
    n_valid: np.ndarray        # [T, D] số khoảng đo hợp lệ dùng để tính
    info: pd.DataFrame         # thông tin detector (tier, vị trí, ...), cùng thứ tự detids
    dropped: dict = field(default_factory=dict)

    @property
    def T(self) -> int:
        return len(self.days) * SLOTS

    @property
    def D(self) -> int:
        return len(self.detids)

    def t_index(self, day: str, slot: int) -> int:
        return self.days.index(day) * SLOTS + int(slot)

    def day_of(self, t: int) -> str:
        return self.days[t // SLOTS]

    def day_index(self, day: str) -> int:
        return self.days.index(day)


def _pivot(df: pd.DataFrame, col: str, days: list[str], detids: list[str]) -> np.ndarray:
    day_ix = {d: i for i, d in enumerate(days)}
    det_ix = {d: i for i, d in enumerate(detids)}
    out = np.full((len(days) * SLOTS, len(detids)), np.nan, dtype=np.float32)
    t = df["day"].map(day_ix).to_numpy() * SLOTS + df["slot"].to_numpy()
    j = df["detid"].map(det_ix).to_numpy()
    out[t, j] = df[col].to_numpy(dtype=np.float32)
    return out


def build_grid(cfg: dict, windows: pd.DataFrame, detectors: pd.DataFrame, hist_end: str | None = None) -> Grid:
    """hist_end: ngày đầu tiên KHÔNG được dùng để xác định tier / detector ngừng gửi / thống kê mô tả.

    Mặc định = ngày bắt đầu phát lại. Giai đoạn kiểm định truyền ngày đầu tháng 5 để tháng 5 không ảnh hưởng
    tới các đại lượng dùng khi chọn mô hình, trọng số, ngưỡng (tránh rò rỉ thông tin).
    """
    dq = cfg["data_quality"]
    hist_end = hist_end or cfg["split"]["replay_start"]
    dropped = {}
    n0 = len(windows)
    windows = windows[(windows["slot"] >= 0) & (windows["slot"] < SLOTS)]
    dropped["slot_out_of_range"] = int(n0 - len(windows))   # slot 96 = khoảng đo 86400 s (rollover)

    days = sorted(windows["day"].unique())
    # đủ mọi ngày liên tục trong khoảng
    days = pd.date_range(days[0], days[-1], freq="D").strftime("%Y-%m-%d").tolist()
    detids = sorted(windows["detid"].unique())

    # Tier xác định chỉ từ lịch sử (trước ngày bắt đầu phát lại) để không nhìn trước tương lai
    hist = windows[windows["day"] < hist_end]
    q = hist.groupby("detid").agg(rows=("n", "sum"), err_rows=("n_err", "sum"))
    q["error_pct"] = (100 * q["err_rows"] / q["rows"]).round(2)
    a, b = dq["tier_a_max_error_pct"], dq["tier_b_max_error_pct"]
    q["tier"] = np.where(q["error_pct"] <= a, "A", np.where(q["error_pct"] <= b, "B", "C"))
    q = q.reindex(detids)

    piv = {c: _pivot(windows, c, days, detids) for c in
           ["n", "n_err", "n_occ", "n_occ_clean", "n_flow", "n_flow_clean",
            "mean_occ_all", "mean_flow_all", "mean_occ_clean", "mean_flow_clean"]}
    use_clean = np.isin(q["tier"].to_numpy(), ["A", "B"])[None, :]
    occ = np.where(use_clean, piv["mean_occ_clean"], piv["mean_occ_all"])
    flow = np.where(use_clean, piv["mean_flow_clean"], piv["mean_flow_all"])
    n_valid = np.where(use_clean, np.minimum(piv["n_occ_clean"], piv["n_flow_clean"]),
                       np.minimum(piv["n_occ"], piv["n_flow"]))
    n_valid = np.nan_to_num(n_valid)

    bad = (n_valid < dq["min_valid_intervals"]) | (occ > dq["occ_max"]) | (flow > dq["flow_max"]) | (occ < 0) | (flow < 0)
    stuck = (occ >= dq["stuck_occ"]) & (flow == 0)
    bad |= stuck
    occ = np.where(bad, np.nan, occ).astype(np.float32)
    flow = np.where(bad, np.nan, flow).astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        err_ratio = (piv["n_err"] / piv["n"]).astype(np.float32)

    # Tỷ lệ khung dùng được (trong lịch sử) → nhóm X = cần bảo trì, không chấm điểm
    t_hist = days.index(hist_end) * SLOTS if hist_end in days else len(days) * SLOTS
    present = ~np.isnan(piv["n"][:t_hist])
    usable = ~np.isnan(occ[:t_hist])
    with np.errstate(invalid="ignore", divide="ignore"):
        usable_ratio = usable.sum(0) / np.maximum(present.sum(0), 1)
    stuck_ratio = stuck[:t_hist].sum(0) / np.maximum(present.sum(0), 1)
    q["usable_ratio"] = np.round(usable_ratio, 4)
    q["stuck_ratio"] = np.round(stuck_ratio, 4)
    q["days_with_data"] = present.reshape(-1, SLOTS, len(detids)).any(1).sum(0)
    # Ngày cuối cùng có số đo trong lịch sử → detector ngừng gửi dữ liệu trước ngày phát lại
    has_day = present.reshape(-1, SLOTS, len(detids)).any(1)
    last_ix = np.where(has_day.any(0), has_day.shape[0] - 1 - np.argmax(has_day[::-1], axis=0), -1)
    q["last_seen"] = [days[i] if i >= 0 else None for i in last_ix]
    offline = last_ix < (t_hist // SLOTS) - dq.get("offline_after_days", 7)
    stuck_x = usable_ratio < dq["min_usable_ratio"]
    is_x = stuck_x | offline
    q["x_reason"] = np.where(offline, "Ngừng gửi dữ liệu", np.where(stuck_x, "Cảm biến kẹt / lỗi", ""))
    q.loc[is_x, "tier"] = "X"
    occ[:, is_x] = np.nan
    flow[:, is_x] = np.nan

    info = q.reset_index().merge(detectors, on="detid", how="left")
    info["mean_occ"] = np.nanmean(np.where(np.isnan(occ[:t_hist]), np.nan, occ[:t_hist]), axis=0) if t_hist else np.nan
    info["mean_flow"] = np.nanmean(flow[:t_hist], axis=0) if t_hist else np.nan
    info = info.set_index("detid").reindex(detids).reset_index()
    dropped["stuck_windows"] = int(stuck.sum())
    dropped["invalid_windows"] = int(bad.sum())
    return Grid(detids, days, occ, flow, err_ratio, n_valid.astype(np.float32), info, dropped)
