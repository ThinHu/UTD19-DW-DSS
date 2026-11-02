"""Engine chạy "live": nhận từng khung 15 phút mới, chấm điểm ngay và lưu kết quả.

Nguồn khung mới có hai đường:
  * Phát lại (replay): lấy khung kế tiếp của tháng 6/2015 từ DW — mô phỏng luồng cảm biến.
  * Nạp ngoài (ingest): POST một bảng khung 15 phút (cùng cấu trúc mart.dss_detector_window),
    dùng khi có dữ liệu thật mới (ví dụ nửa cuối năm 2015).
Cả hai đều đi qua cùng hàm `_score_range`, dùng chung lõi tính toán với bước build.
"""
from __future__ import annotations

import copy
import json
import threading

import joblib
import numpy as np
import pandas as pd

from . import baseline as B
from . import engine as E
from . import scoring as S
from .build import _block, _day_types, to_c5
from .config import artifacts_dir, load_config, resolve
from .data import SLOTS
from .store import ResultStore


def slot_label(slot: int) -> str:
    return f"{slot // 4:02d}:{(slot % 4) * 15:02d}"


class LiveEngine:
    def __init__(self, cfg_path=None):
        self.cfg = cfg = load_config(cfg_path)
        art = artifacts_dir(cfg)
        if not (art / "meta.json").exists():
            raise SystemExit("Chưa có artifacts. Chạy trước: python -m utd19_dss.build")
        self.meta = json.loads((art / "meta.json").read_text(encoding="utf-8"))
        self.src_grid = joblib.load(art / "grid.joblib")            # dữ liệu nguồn đầy đủ (feeder)
        self.base = B.Baseline.from_npz(art / "baseline_final.npz")
        bundle = joblib.load(art / "model.joblib")
        self.model, self.model_name = bundle["model"], bundle["name"]
        self.feature_names, self.tree = bundle["features"], bundle["explain_tree"]
        self.static = np.load(art / "static_features.npy")
        info = pd.read_csv(art / "detector_info.csv", encoding="utf-8-sig")
        self.info = info.set_index("detid").loc[self.src_grid.detids].reset_index()
        self.day_type = _day_types(self.src_grid, cfg)
        W, self.dist = E.neighbor_matrix(cfg, self.info)
        self.ctx = {"W": W, "ref": self.info["tier"].eq("A").to_numpy()}
        self.weights = {k: float(v) for k, v in self.meta["weights"].items()}
        self.thresholds = dict(self.meta["thresholds"])
        if "max_high" not in self.thresholds and cfg["scoring"].get("max_high_per_window"):
            self.thresholds["max_high"] = int(cfg["scoring"]["max_high_per_window"])   # artifacts dựng trước khi có giới hạn
        self.t_rep0 = self.src_grid.t_index(cfg["split"]["replay_start"], 0)
        self.T = self.src_grid.T
        self.D = self.src_grid.D
        self.tier = self.info["tier"].to_numpy()
        self.store = ResultStore(resolve(cfg, cfg["results_db"]))
        self.lock = threading.RLock()
        self.playing = not cfg["replay"]["start_paused"]
        self.tick_seconds = float(cfg["replay"]["tick_seconds"])
        self.reset()

    # ------------------------------------------------------------------
    # Trạng thái
    # ------------------------------------------------------------------
    def reset(self):
        with self.lock:
            g = copy.copy(self.src_grid)
            g.occ = self.src_grid.occ.copy(); g.flow = self.src_grid.flow.copy()
            g.err_ratio = self.src_grid.err_ratio.copy(); g.n_valid = self.src_grid.n_valid.copy()
            for a in (g.occ, g.flow, g.err_ratio):
                a[self.t_rep0:] = np.nan
            g.n_valid[self.t_rep0:] = 0
            self.grid = g
            n = self.T - self.t_rep0
            self.C = np.full((n, self.D, 5), np.nan, dtype=np.float32)
            self.P = np.full((n, self.D), np.nan, dtype=np.float32)
            self.z_occ = np.full((n, self.D), np.nan, dtype=np.float32)
            self.z_flow = np.full((n, self.D), np.nan, dtype=np.float32)
            self.event = np.full((n, self.D), np.nan, dtype=np.float32)
            self.mu_occ = np.full((n, self.D), np.nan, dtype=np.float32)
            self.mu_flow = np.full((n, self.D), np.nan, dtype=np.float32)
            self.Xlast = None
            self.next_t = self.t_rep0          # khung kế tiếp chưa nhận
            self.source = "replay"
            self.store.clear_live()
            self.advance(1)                    # khung đầu tiên 01/06 00:00

    @property
    def now_t(self) -> int:
        return self.next_t - 1

    def now(self) -> dict:
        t = self.now_t
        day, slot = self.grid.day_of(t), t % SLOTS
        return {"t": t, "day": day, "slot": int(slot), "label": slot_label(slot),
                "day_type": B.DAY_TYPE_LABEL[self.day_type[t // SLOTS]],
                "progress": round((t - self.t_rep0 + 1) / (self.T - self.t_rep0), 4),
                "replay_end": self.next_t >= self.T}

    # ------------------------------------------------------------------
    # Nhận khung mới
    # ------------------------------------------------------------------
    def advance(self, n: int = 1) -> int:
        """Phát lại n khung kế tiếp từ nguồn (mô phỏng cảm biến gửi dữ liệu)."""
        with self.lock:
            a = self.next_t
            b = min(self.T, a + n)
            if b <= a:
                return 0
            for name in ("occ", "flow", "err_ratio", "n_valid"):
                getattr(self.grid, name)[a:b] = getattr(self.src_grid, name)[a:b]
            self._score_range(a, b)
            self.next_t = b
            return b - a

    def ingest(self, df: pd.DataFrame) -> dict:
        """Nạp một khung 15 phút từ nguồn ngoài (đúng khung kế tiếp)."""
        from .data import _normalize
        df = _normalize(df)
        keys = df[["day", "slot"]].drop_duplicates()
        if len(keys) != 1:
            raise ValueError("Mỗi lần nạp chỉ một khung (day, slot)")
        day, slot = keys.iloc[0]["day"], int(keys.iloc[0]["slot"])
        if day not in self.grid.days:
            raise ValueError(f"Ngày {day} nằm ngoài phạm vi lưới hiện tại")
        t = self.grid.t_index(day, slot)
        if t != self.next_t:
            raise ValueError(f"Khung kế tiếp phải là {self.grid.day_of(self.next_t)} {slot_label(self.next_t % SLOTS)}")
        dq = self.cfg["data_quality"]
        with self.lock:
            det_ix = {d: i for i, d in enumerate(self.grid.detids)}
            df = df[df["detid"].isin(det_ix)]
            j = df["detid"].map(det_ix).to_numpy()
            cleanmode = np.isin(self.tier[j], ["A", "B"])
            occ = np.where(cleanmode, df["mean_occ_clean"], df["mean_occ_all"]).astype(float)
            flow = np.where(cleanmode, df["mean_flow_clean"], df["mean_flow_all"]).astype(float)
            nv = np.where(cleanmode, np.minimum(df["n_occ_clean"], df["n_flow_clean"]),
                          np.minimum(df["n_occ"], df["n_flow"])).astype(float)
            bad = (nv < dq["min_valid_intervals"]) | (occ > dq["occ_max"]) | (flow > dq["flow_max"]) | \
                  ((occ >= dq["stuck_occ"]) & (flow == 0)) | (self.tier[j] == "X")
            for arr in (self.grid.occ, self.grid.flow, self.grid.err_ratio):
                arr[t] = np.nan
            self.grid.occ[t, j] = np.where(bad, np.nan, occ)
            self.grid.flow[t, j] = np.where(bad, np.nan, flow)
            self.grid.err_ratio[t, j] = (df["n_err"] / df["n"]).to_numpy(float)
            self.grid.n_valid[t] = 0
            self.grid.n_valid[t, j] = nv
            self._score_range(t, t + 1)
            self.next_t = t + 1
            self.source = "ingest"
        return {"day": day, "slot": slot, "rows": int(len(df)), "valid": int((~bad).sum())}

    def seek(self, day: str, slot: int):
        t = self.grid.t_index(day, slot)
        if t < self.t_rep0:
            raise ValueError("Chỉ phát lại trong giai đoạn live (từ 01/06/2015)")
        with self.lock:
            if t < self.next_t:            # lùi lại: phát lại từ đầu tới khung đích
                self.reset()
            self.advance(t + 1 - self.next_t)

    # ------------------------------------------------------------------
    # Chấm điểm
    # ------------------------------------------------------------------
    def _score_range(self, a: int, b: int):
        lo = max(a - E.LAGS - 1, 0)
        ex, blk, X = _block(self.cfg, self.grid, self.base, self.day_type, self.ctx, self.static, lo, b)
        k = a - lo
        sl = slice(a - self.t_rep0, b - self.t_rep0)
        ok = ~np.isnan(blk["z_occ"][k:])
        P = np.full(ok.shape, np.nan, dtype=np.float32)
        if ok.any():
            P[ok] = self.model.predict_proba(X[k:][ok])[:, 1]
        self.P[sl] = P
        self.C[sl] = np.stack([blk["C1"][k:], blk["C2"][k:], blk["C3"][k:], blk["C4"][k:], to_c5(P, self.cfg)], -1)
        self.z_occ[sl] = blk["z_occ"][k:]; self.z_flow[sl] = blk["z_flow"][k:]
        self.event[sl] = blk["E"][k:]
        self.mu_occ[sl] = ex["mu_occ"][k:]; self.mu_flow[sl] = ex["mu_flow"][k:]
        self.Xlast = X[-1]
        self.store.write_windows(self, a, b)

    def score_matrix(self, weights=None, thresholds=None, t=None):
        t = self.now_t if t is None else t
        r = t - self.t_rep0
        w = weights or self.weights
        th = thresholds or self.thresholds
        sc = S.priority(self.C[r], w)
        return sc, S.level(sc, th), S.top_factor(self.C[r], w)

    def window_table(self, t=None, weights=None, thresholds=None) -> pd.DataFrame:
        t = self.now_t if t is None else t
        r = t - self.t_rep0
        sc, lvl, top = self.score_matrix(weights, thresholds, t)
        C = self.C[r]
        conf = S.confidence(self.tier, self.grid.n_valid[t], ~np.isnan(sc))
        over = S.overflow(sc, thresholds or self.thresholds)
        acts = [S.action(l, tp, {k: (None if np.isnan(C[i, j]) else float(C[i, j])) for j, k in enumerate(S.KEYS)},
                         None if np.isnan(self.z_flow[r, i]) else float(self.z_flow[r, i]), self.tier[i], bool(over[i]))
                for i, (l, tp) in enumerate(zip(lvl, top))]
        prev_sc = None
        if r > 0:
            prev_sc, _, _ = self.score_matrix(weights, thresholds, t - 1)
        df = pd.DataFrame({
            "detid": self.grid.detids, "road": self.info["road"], "fclass": self.info["fclass"],
            "lat": self.info["lat"], "long": self.info["long"], "tier": self.tier,
            "cluster": self.info["cluster"], "x_reason": self.info["x_reason"].fillna(""),
            "score": np.round(sc, 1), "level": lvl,
            "top_factor": [S.FACTOR_LABELS[x] if s == s else "" for x, s in zip(top, sc)],
            "top_key": [x if s == s else "" for x, s in zip(top, sc)],
            "action_code": [a[0] for a in acts], "action": [a[1] for a in acts],
            "confidence": conf,
            "C1": np.round(C[:, 0], 1), "C2": np.round(C[:, 1], 1), "C3": np.round(C[:, 2], 1),
            "C4": np.round(C[:, 3], 1), "C5": np.round(C[:, 4], 1),
            "p_event30": np.round(self.P[r], 3),
            "certainty": np.round(S.certainty(sc, self.meta.get("certainty_curve", [np.nan] * 101)), 3),
            "occ": np.round(self.grid.occ[t], 4), "flow": np.round(self.grid.flow[t], 1),
            "mu_occ": np.round(self.mu_occ[r], 4), "mu_flow": np.round(self.mu_flow[r], 1),
            "z_occ": np.round(self.z_occ[r], 2), "z_flow": np.round(self.z_flow[r], 2),
            "delta": np.round(sc - prev_sc, 1) if prev_sc is not None else np.nan,
            "status": np.where(self.tier == "X", "Offline",
                               np.where(np.isnan(self.grid.occ[t]), "Thiếu số đo", "Live")),
        })
        df["rank"] = df["score"].rank(ascending=False, method="first")
        return df.sort_values(["score"], ascending=False, na_position="last")

    def explain(self, detid: str, t=None) -> list[str]:
        """Diễn giải bằng luật của cây quyết định (đường đi từ gốc tới lá) cho detector ở khung t."""
        t = self.now_t if t is None else t
        i = self.grid.detids.index(detid)
        lo = max(t - E.LAGS - 1, 0)
        ex, blk, X = _block(self.cfg, self.grid, self.base, self.day_type, self.ctx, self.static, lo, t + 1)
        if np.isnan(blk["z_occ"][-1, i]):
            return []
        x = X[-1, i][None, :]
        tree = self.tree.tree_
        node_ids = self.tree.decision_path(x).indices
        rules = []
        for nd in node_ids:
            f = tree.feature[nd]
            if f < 0:
                val = tree.value[nd][0]
                p = val[1] / val.sum() if val.sum() else 0
                rules.append(f"→ Lá cây: tỷ lệ sự kiện trong 30 phút tới ở các trường hợp tương tự ≈ {p:.0%}")
                continue
            name, thr, v = self.feature_names[f], tree.threshold[nd], x[0, f]
            op = "≤" if v <= thr else ">"
            rules.append(f"{FEATURE_VN.get(name, name)} = {v:.3g} {op} {thr:.3g}")
        return rules


FEATURE_VN = {
    "occ": "Occupancy hiện tại", "occ_minus_mu": "Occupancy vượt kỳ vọng", "flow_ratio": "Lưu lượng / kỳ vọng",
    "z_occ": "z occupancy", "z_flow": "z lưu lượng", "z_occ_l1": "z occupancy khung trước",
    "z_occ_l2": "z occupancy 2 khung trước", "z_occ_l3": "z occupancy 3 khung trước", "dz1": "Biến thiên z",
    "n_lags": "Số khung trễ hợp lệ", "event_now": "Đang có sự kiện", "C3": "Độ kéo dài (C3)",
    "C4": "Lan tỏa lân cận (C4)", "mu_ramp": "Baseline tăng trong 30 phút tới", "city_f_occ": "Hệ số mức chung",
    "err_ratio": "Tỷ lệ khoảng đo lỗi", "hour_sin": "Giờ (sin)", "hour_cos": "Giờ (cos)",
    "dt_WD": "Ngày làm việc", "dt_SAT": "Thứ Bảy", "dt_SUN": "Chủ nhật/Lễ", "det_mean_occ": "Occupancy TB của detector",
    "tier_code": "Tier dữ liệu", "fc_primary": "Đường primary", "fc_secondary": "Đường secondary",
    "fc_tertiary": "Đường tertiary", "fc_other": "Loại đường khác",
}
