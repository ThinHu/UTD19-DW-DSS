"""Mô hình học máy cho tiêu chí C5: dự báo sự kiện ùn tắc bất thường trong 30 phút tới.

So sánh ba thuật toán của Chương 5 (Decision Tree, Naive Bayes, Neural Network) và
Gradient Boosting (mở rộng của Decision Tree) với hai mốc
tham chiếu không học: Persistence (giữ nguyên trạng thái hiện tại) và điểm luật v4 (C1–C4).
"""
from __future__ import annotations

import time

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_curve, roc_auc_score
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

MODEL_LABELS = {
    "dt": "Decision Tree (CART, entropy)",
    "nb": "Naive Bayes (Gaussian)",
    "mlp": "Neural Network (MLP 32-16)",
    "gb": "Gradient Boosting (tập hợp cây quyết định)",
    "persistence": "Persistence (trạng thái hiện tại)",
    "rule_v4": "Điểm luật v4 (C1–C4)",
}


def make_model(name: str, rs: int, **kw):
    if name == "dt":
        return DecisionTreeClassifier(criterion="entropy", max_depth=kw.get("max_depth", 8),
                                      min_samples_leaf=kw.get("min_samples_leaf", 300), random_state=rs)
    if name == "nb":
        return make_pipeline(StandardScaler(), GaussianNB())
    if name == "mlp":
        return make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(32, 16), activation="tanh",
                                                             alpha=1e-4, batch_size=1024, learning_rate_init=1e-3,
                                                             max_iter=40, early_stopping=True, n_iter_no_change=5,
                                                             random_state=rs))
    if name == "gb":
        # Mở rộng của Decision Tree: cộng dồn nhiều cây nông, cây sau sửa sai số của cây trước
        return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, max_leaf_nodes=63,
                                              min_samples_leaf=200, l2_regularization=1.0, early_stopping=True,
                                              validation_fraction=0.1, n_iter_no_change=20, random_state=rs)
    raise ValueError(name)


def sample_rows(n: int, size: int, rs: int) -> np.ndarray:
    if n <= size:
        return np.arange(n)
    return np.random.default_rng(rs).choice(n, size, replace=False)


def evaluate(y: np.ndarray, p: np.ndarray, event_now: np.ndarray) -> dict:
    """Các chỉ số trên tập đánh giá. Ngưỡng chọn theo F1 lớn nhất."""
    out = {"n": int(len(y)), "pos_rate": round(float(y.mean()), 4)}
    out["pr_auc"] = round(float(average_precision_score(y, p)), 4)
    out["roc_auc"] = round(float(roc_auc_score(y, p)), 4)
    out["brier"] = round(float(brier_score_loss(y, np.clip(p, 0, 1))), 4)
    prec, rec, thr = precision_recall_curve(y, p)
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-9)
    i = int(np.nanargmax(f1[:-1])) if len(thr) else 0
    t = float(thr[i]) if len(thr) else 0.5
    pred = p >= t
    tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum()); tn = int((~pred & (y == 0)).sum())
    onset = (y == 1) & (event_now == 0)
    out.update({
        "threshold": round(t, 4), "precision": round(tp / max(tp + fp, 1), 4), "recall": round(tp / max(tp + fn, 1), 4),
        "f1": round(float(f1[i]), 4), "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "onset_recall": round(float(pred[onset].mean()) if onset.any() else 0.0, 4),
        "onset_share": round(float(onset.sum() / max((y == 1).sum(), 1)), 4),
    })
    return out


def fit_and_compare(X_tr, y_tr, X_va, y_va, ev_va, extra_scores: dict, rs: int, cfg_ml: dict, log=print):
    """Huấn luyện DT (quét độ sâu), NB, MLP; trả về bảng so sánh + mô hình tốt nhất mỗi loại."""
    results, fitted = {}, {}
    idx = sample_rows(len(y_tr), cfg_ml["train_sample"], rs)
    Xs, ys = X_tr[idx], y_tr[idx]

    best_dt = None
    dt_scan = []
    for depth in [4, 6, 8, 10, 12]:
        t0 = time.time()
        m = make_model("dt", rs, max_depth=depth).fit(Xs, ys)
        p = m.predict_proba(X_va)[:, 1]
        ap = float(average_precision_score(y_va, p))
        dt_scan.append({"max_depth": depth, "pr_auc": round(ap, 4), "seconds": round(time.time() - t0, 1)})
        log(f"  DT depth={depth}: PR-AUC={ap:.4f}")
        if best_dt is None or ap > best_dt[0]:
            best_dt = (ap, depth, m, p, time.time() - t0)
    _, depth, m, p, sec = best_dt
    fitted["dt"] = m
    results["dt"] = {**evaluate(y_va, p, ev_va), "params": {"max_depth": depth}, "fit_seconds": round(sec, 1)}

    t0 = time.time()
    m = make_model("nb", rs).fit(Xs, ys)
    p = m.predict_proba(X_va)[:, 1]
    fitted["nb"] = m
    results["nb"] = {**evaluate(y_va, p, ev_va), "params": {}, "fit_seconds": round(time.time() - t0, 1)}
    log(f"  NB: PR-AUC={results['nb']['pr_auc']:.4f}")

    t0 = time.time()
    idx2 = sample_rows(len(y_tr), cfg_ml["mlp_sample"], rs + 1)
    m = make_model("mlp", rs).fit(X_tr[idx2], y_tr[idx2])
    p = m.predict_proba(X_va)[:, 1]
    fitted["mlp"] = m
    results["mlp"] = {**evaluate(y_va, p, ev_va), "params": {"hidden": [32, 16], "activation": "tanh",
                                                             "epochs": int(m[-1].n_iter_)},
                      "fit_seconds": round(time.time() - t0, 1)}
    log(f"  MLP: PR-AUC={results['mlp']['pr_auc']:.4f}")

    t0 = time.time()
    m = make_model("gb", rs).fit(Xs, ys)
    p = m.predict_proba(X_va)[:, 1]
    fitted["gb"] = m
    results["gb"] = {**evaluate(y_va, p, ev_va), "params": {"trees": int(m.n_iter_), "max_leaf_nodes": 63},
                     "fit_seconds": round(time.time() - t0, 1)}
    log(f"  GB: PR-AUC={results['gb']['pr_auc']:.4f}")

    for name, s in extra_scores.items():
        results[name] = {**evaluate(y_va, s, ev_va), "params": {}, "fit_seconds": 0.0}
        log(f"  {name}: PR-AUC={results[name]['pr_auc']:.4f}")
    return results, fitted, dt_scan
