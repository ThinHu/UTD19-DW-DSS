"""Priority Score, mức ưu tiên, yếu tố chính, gợi ý hành động (bảng quyết định) và độ tin cậy."""
from __future__ import annotations

import numpy as np

KEYS = ["C1", "C2", "C3", "C4", "C5"]
FACTOR_LABELS = {
    "C1": "Occupancy cao hơn thường lệ",
    "C2": "Lưu lượng bất thường",
    "C3": "Bất thường kéo dài",
    "C4": "Ảnh hưởng từ detector lân cận",
    "C5": "Nguy cơ ùn tắc 30 phút tới (ML)",
}
LEVELS = ["Cao", "Trung bình", "Thấp", "Không đủ dữ liệu"]


def priority(C: np.ndarray, weights: dict) -> np.ndarray:
    """C: [..., 5] theo thứ tự KEYS. Tiêu chí thiếu thì bỏ và chuẩn hóa lại trọng số; C1, C2 bắt buộc."""
    Wv = np.array([weights[k] for k in KEYS], dtype=np.float32)
    avail = ~np.isnan(C)
    contrib = np.where(avail, C * Wv, 0.0)
    wsum = (avail * Wv).sum(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = contrib.sum(-1) / wsum
    core = avail[..., 0] & avail[..., 1]
    return np.where(core, s, np.nan)


def level(score: np.ndarray, th: dict) -> np.ndarray:
    """Mức ưu tiên. score: [D] (một khung) hoặc [T, D] (mỗi hàng một khung).

    Nếu th có "max_high" > 0 (năng lực ca trực): trong mỗi khung chỉ N detector điểm cao nhất được giữ mức Cao,
    phần còn lại có điểm ≥ ngưỡng Cao bị hạ xuống Trung bình (hàng chờ — xem overflow()).
    """
    lv = np.select([score >= th["high"], score >= th["medium"], ~np.isnan(score)],
                   ["Cao", "Trung bình", "Thấp"], default="Không đủ dữ liệu")
    over = overflow(score, th)
    return np.where(over, "Trung bình", lv) if over.any() else lv


def overflow(score: np.ndarray, th: dict) -> np.ndarray:
    """True ở detector có điểm ≥ ngưỡng Cao nhưng nằm ngoài top-N của khung (N = th["max_high"])."""
    cap = int(th.get("max_high") or 0)
    s = np.asarray(score, dtype=np.float64)
    if cap <= 0 or s.ndim == 0:
        return np.zeros(s.shape, dtype=bool)
    s2 = s.reshape(-1, s.shape[-1])
    hi = np.nan_to_num(s2, nan=-1.0) >= th["high"]
    out = np.zeros_like(hi)
    rows = np.where(hi.sum(1) > cap)[0]
    if len(rows):
        order = np.argsort(-np.nan_to_num(s2[rows], nan=-1.0), axis=1, kind="stable")
        rank = np.empty_like(order)
        np.put_along_axis(rank, order, np.arange(s2.shape[1])[None, :].repeat(len(rows), 0), axis=1)
        out[rows] = hi[rows] & (rank >= cap)
    return out.reshape(s.shape)


def top_factor(C: np.ndarray, weights: dict) -> np.ndarray:
    Wv = np.array([weights[k] for k in KEYS], dtype=np.float32)
    v = np.where(np.isnan(C), -1, C * Wv)
    return np.array(KEYS)[np.argmax(v, axis=-1)]


def confidence(tier: np.ndarray, n_valid: np.ndarray, scored: np.ndarray) -> np.ndarray:
    conf = np.where((tier == "A") & (n_valid >= 4), "Cao",
                    np.where(tier == "A", "Trung bình", np.where(tier == "B", "Thấp", "Rất thấp")))
    return np.where(scored, conf, "")


def action(lvl: str, top: str, C: dict, z_flow: float, tier: str, over: bool = False) -> tuple[str, str]:
    """Bảng quyết định (mục 2.5 tài liệu thiết kế). Trả về (mã hành động, mô tả).

    over=True: điểm đạt mức Cao nhưng khung đã đủ N cảnh báo Cao (năng lực ca trực) → hàng chờ.
    """
    if tier == "X":
        return "MAINT", "Thiết bị cần bảo trì — không chấm điểm"
    if lvl == "Không đủ dữ liệu":
        return "NODATA", "Không đủ dữ liệu tin cậy trong khung này"
    if over:
        return "QUEUE", "Hàng chờ: điểm mức Cao nhưng ca trực đã đủ số cảnh báo — xử lý khi có người rảnh"
    if lvl == "Thấp":
        return "NORMAL", "Hoạt động bình thường"
    c1, c3, c5 = C.get("C1") or 0, C.get("C3") or 0, C.get("C5") or 0
    if lvl == "Trung bình":
        if c5 >= 50:
            return "WATCH_RISK", "Theo dõi sát — mô hình dự báo nguy cơ ùn trong 30 phút tới"
        return "WATCH", "Theo dõi sát, chưa cần can thiệp"
    # Mức Cao
    if tier == "C":
        return "VERIFY", "Xác minh bằng camera/thiết bị trước khi điều phối (dữ liệu độ tin cậy rất thấp)"
    if top == "C5" and c1 < 50:
        return "EARLY", "Cảnh báo sớm: chuẩn bị kịch bản điều chỉnh pha đèn trong 15–30 phút tới"
    if c3 >= 75:
        return "PERSIST", "Ùn kéo dài: điều phối hiện trường, phát thông báo VMS / gợi ý đường vòng"
    if top == "C4":
        return "AREA", "Ùn lan theo khu vực: phối hợp điều chỉnh tín hiệu các nút lân cận"
    if top == "C2" and z_flow is not None and z_flow < 0 and c1 >= 50:
        return "INCIDENT", "Lưu lượng giảm khi occupancy tăng: nghi sự cố chắn làn, kiểm tra camera"
    if top == "C2" and z_flow is not None and z_flow > 0:
        return "SURGE", "Lưu lượng tăng đột biến: tăng thời gian xanh cho hướng này"
    return "INTERVENE", "Ưu tiên kiểm tra và can thiệp trong ca"


# Bảng quyết định dạng bảng (cùng thứ tự luật với action(); luật đầu tiên khớp được áp dụng)
DECISION_TABLE = [
    {"rule": 1, "level": "—", "condition": "Detector tier X (kẹt / ngừng gửi dữ liệu)", "code": "MAINT"},
    {"rule": 2, "level": "Không đủ dữ liệu", "condition": "Thiếu C1 hoặc C2 trong khung", "code": "NODATA"},
    {"rule": 3, "level": "Trung bình (hạ từ Cao)", "condition": "Điểm ≥ ngưỡng Cao nhưng ngoài top-N của khung (N = năng lực ca trực)", "code": "QUEUE"},
    {"rule": 4, "level": "Thấp", "condition": "Điểm < ngưỡng Trung bình", "code": "NORMAL"},
    {"rule": 5, "level": "Trung bình", "condition": "C5 ≥ 50", "code": "WATCH_RISK"},
    {"rule": 6, "level": "Trung bình", "condition": "Còn lại", "code": "WATCH"},
    {"rule": 7, "level": "Cao", "condition": "Detector tier C (độ tin cậy dữ liệu rất thấp)", "code": "VERIFY"},
    {"rule": 8, "level": "Cao", "condition": "Yếu tố chính là C5 và C1 < 50 (chưa ùn nhưng sắp ùn)", "code": "EARLY"},
    {"rule": 9, "level": "Cao", "condition": "C3 ≥ 75 (bất thường ≥ 3/4 khung gần nhất)", "code": "PERSIST"},
    {"rule": 10, "level": "Cao", "condition": "Yếu tố chính là C4 (lân cận cùng bất thường)", "code": "AREA"},
    {"rule": 11, "level": "Cao", "condition": "Yếu tố chính C2, z lưu lượng < 0 và C1 ≥ 50", "code": "INCIDENT"},
    {"rule": 12, "level": "Cao", "condition": "Yếu tố chính C2, z lưu lượng > 0", "code": "SURGE"},
    {"rule": 13, "level": "Cao", "condition": "Còn lại", "code": "INTERVENE"},
]

ACTION_CODES = {
    "EARLY": "Cảnh báo sớm", "PERSIST": "Ùn kéo dài", "AREA": "Ùn lan khu vực", "INCIDENT": "Nghi sự cố",
    "SURGE": "Tăng đột biến", "INTERVENE": "Can thiệp", "VERIFY": "Xác minh thiết bị",
    "QUEUE": "Hàng chờ (vượt năng lực)", "WATCH_RISK": "Theo dõi (có nguy cơ)", "WATCH": "Theo dõi", "NORMAL": "Bình thường",
    "NODATA": "Thiếu dữ liệu", "MAINT": "Bảo trì",
}


# ---------------------------------------------------------------------------
# Tối ưu trọng số trên tập kiểm định (lưới tìm kiếm, ràng buộc tổng = 1)
# ---------------------------------------------------------------------------
def weight_grid(lo: float, hi: float, step: float) -> np.ndarray:
    vals = np.round(np.arange(lo, hi + 1e-9, step), 4)
    out = []
    for a in vals:
        for b in vals:
            for c in vals:
                for d in vals:
                    e = round(1 - a - b - c - d, 4)
                    if lo - 1e-9 <= e <= hi + 1e-9:
                        out.append((a, b, c, d, e))
    return np.array(out, dtype=np.float32)


def precision_at_k(score: np.ndarray, target: np.ndarray, k: int, active: np.ndarray) -> float:
    """score, target: [T, D]. Trung bình precision@k trên các khung 'active' (có ≥1 mục tiêu)."""
    s = np.where(np.isnan(score), -1, score)
    idx = np.argpartition(-s, k, axis=1)[:, :k]
    hit = np.take_along_axis(np.nan_to_num(target), idx, axis=1).sum(1) / k
    return float(hit[active].mean())


def optimise_weights(C: np.ndarray, target: np.ndarray, k: int, lo: float, hi: float, step: float):
    """C: [T, D, 5]. Trả về (trọng số tốt nhất, bảng kết quả)."""
    grid = weight_grid(lo, hi, step)
    active = (np.nan_to_num(target) > 0).any(1)
    res = []
    for w in grid:
        sc = priority(C, dict(zip(KEYS, w)))
        res.append(precision_at_k(sc, target, k, active))
    res = np.array(res)
    best = grid[int(np.argmax(res))]
    return dict(zip(KEYS, [round(float(x), 2) for x in best])), grid, res


def certainty_curve(score: np.ndarray, target: np.ndarray) -> list[float]:
    """Hiệu chỉnh isotonic: P(detector thật sự cần chú ý | điểm = s) cho s = 0..100.

    Dựng trên tập kiểm định; dùng làm "độ chắc chắn" của khuyến nghị và để đặt ngưỡng.
    """
    from sklearn.isotonic import IsotonicRegression
    s = score.ravel(); y = np.nan_to_num(target.ravel())
    ok = ~np.isnan(s)
    iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip").fit(s[ok], y[ok])
    return [round(float(v), 4) for v in iso.predict(np.arange(101, dtype=float))]


def certainty(score: np.ndarray, curve: list[float]) -> np.ndarray:
    c = np.asarray(curve, dtype=np.float32)
    idx = np.clip(np.nan_to_num(np.round(score), nan=0), 0, 100).astype(int)
    return np.where(np.isnan(score), np.nan, c[idx])


def threshold_sweep(score: np.ndarray, target: np.ndarray, event_now: np.ndarray | None = None,
                    lo: int = 15, hi: int = 80, step: int = 5) -> list[dict]:
    """Quét ngưỡng: với mỗi t, coi "điểm ≥ t" là cảnh báo và đo so với nhãn cần chú ý (target)."""
    s = np.nan_to_num(score, nan=-1.0)
    y = np.nan_to_num(target) > 0
    now = (np.nan_to_num(event_now) > 0) if event_now is not None else None
    fut = (y & ~now) if now is not None else None
    out = []
    for t in range(lo, hi + 1, step):
        a = s >= t
        tp = float((a & y).sum())
        prec = tp / max(float(a.sum()), 1.0)
        rec = tp / max(float(y.sum()), 1.0)
        f = lambda b: (1 + b * b) * prec * rec / max(b * b * prec + rec, 1e-12)
        r = {"threshold": t, "alerts_per_window": round(float(a.sum(1).mean()), 2), "precision": round(prec, 4),
             "recall": round(rec, 4), "f1": round(f(1), 4), "f2": round(f(2), 4), "f05": round(f(0.5), 4)}
        if now is not None:
            r["recall_now"] = round(float((a & now).sum() / max(now.sum(), 1)), 4)
            r["recall_future"] = round(float((a & fut).sum() / max(fut.sum(), 1)), 4)
        out.append(r)
    return out


def select_thresholds(sweep: list[dict], rule: dict) -> dict:
    """Chọn ngưỡng theo F-score trên tập kiểm định.

    Cao (hành động ngay): ngưỡng có F1 lớn nhất — cân bằng cảnh báo đúng và không bỏ sót.
    Trung bình (theo dõi): ngưỡng thấp hơn Cao có F_beta lớn nhất (mặc định F2: bỏ sót nặng gấp đôi
    cảnh báo thừa, vì mức theo dõi không tốn nguồn lực can thiệp).
    """
    hk, mk = rule.get("high", "f1"), rule.get("medium", "f2")
    best_h = max(sweep, key=lambda r: (r[hk], r["threshold"]))
    cand = [r for r in sweep if r["threshold"] < best_h["threshold"]]
    best_m = max(cand, key=lambda r: (r[mk], -r["threshold"])) if cand else {"threshold": max(10, best_h["threshold"] - 10)}
    return {"high": int(best_h["threshold"]), "medium": int(best_m["threshold"])}


# ---------------------------------------------------------------------------
# Goal seeking (Chương 7): cho trước mục tiêu kết quả, tìm giá trị biến quyết định (ngưỡng mức Cao)
# ---------------------------------------------------------------------------
GOALS = {
    "precision": ("Precision mức Cao ≥", "lowest"),        # đạt độ đúng tối thiểu, giữ recall cao nhất
    "recall": ("Recall mức Cao ≥", "highest"),             # không bỏ sót quá mức, giữ precision cao nhất
    "alerts": ("Số cảnh báo Cao ở 95% khung ≤", "lowest"),  # năng lực ca trực (nguồn lực có hạn), tính cả giờ cao điểm
}


def threshold_curve(score: np.ndarray, target: np.ndarray, lo: int = 5, hi: int = 95) -> list[dict]:
    """Precision / recall / số cảnh báo mỗi khung theo ngưỡng nguyên lo..hi (dùng cho goal seeking)."""
    s = np.nan_to_num(score, nan=-1.0)
    y = np.nan_to_num(target) > 0
    ny = max(float(y.sum()), 1.0)
    out = []
    for t in range(lo, hi + 1):
        a = s >= t
        na = float(a.sum())
        tp = float((a & y).sum())
        per_win = a.sum(1)
        out.append({"threshold": t, "precision": round(tp / na, 4) if na else None, "recall": round(tp / ny, 4),
                    "alerts_per_window": round(na / s.shape[0], 3),
                    "alerts_p95": float(np.quantile(per_win, 0.95)), "alerts_max": int(per_win.max())})
    return out


def goal_seek(curve: list[dict], goal: str, value: float) -> dict | None:
    """Chọn ngưỡng thỏa mục tiêu. Trả về dòng của curve, hoặc None nếu không ngưỡng nào đạt."""
    if goal == "precision":
        ok = [r for r in curve if r["precision"] is not None and r["precision"] >= value]
        return min(ok, key=lambda r: r["threshold"]) if ok else None
    if goal == "recall":
        ok = [r for r in curve if r["recall"] >= value]
        return max(ok, key=lambda r: r["threshold"]) if ok else None
    if goal == "alerts":
        ok = [r for r in curve if r["alerts_p95"] <= value]
        return min(ok, key=lambda r: r["threshold"]) if ok else None
    raise ValueError(goal)
