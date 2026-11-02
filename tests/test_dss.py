"""Kiểm thử engine DSS v5."""
import numpy as np
import pytest

from utd19_dss import scoring as S
from utd19_dss.config import artifacts_dir, load_config


def test_priority_renormalises_missing_criteria():
    w = {"C1": 0.3, "C2": 0.05, "C3": 0.05, "C4": 0.1, "C5": 0.5}
    C = np.array([[100, 0, np.nan, np.nan, 0]], dtype=np.float32)
    s = S.priority(C, w)[0]
    assert s == pytest.approx(100 * 0.3 / (0.3 + 0.05 + 0.5))


def test_priority_requires_c1_c2():
    w = {"C1": 0.3, "C2": 0.05, "C3": 0.05, "C4": 0.1, "C5": 0.5}
    C = np.array([[np.nan, 10, 10, 10, 10]], dtype=np.float32)
    assert np.isnan(S.priority(C, w)[0])


def test_levels_and_actions():
    lvl = S.level(np.array([80, 30, 5, np.nan]), {"high": 35, "medium": 20})
    assert list(lvl) == ["Cao", "Trung bình", "Thấp", "Không đủ dữ liệu"]
    code, _ = S.action("Cao", "C5", {"C1": 10, "C3": 0, "C5": 90}, 0.5, "A")
    assert code == "EARLY"
    code, _ = S.action("Cao", "C1", {"C1": 90, "C3": 100, "C5": 60}, 0.5, "A")
    assert code == "PERSIST"
    assert S.action("Cao", "C1", {}, 0, "X")[0] == "MAINT"


def test_weight_grid_sums_to_one():
    g = S.weight_grid(0.05, 0.5, 0.05)
    assert np.allclose(g.sum(1), 1, atol=1e-4)
    assert g.min() >= 0.05 - 1e-6 and g.max() <= 0.5 + 1e-6


@pytest.mark.skipif(not (artifacts_dir(load_config()) / "meta.json").exists(), reason="chưa chạy build")
def test_live_matches_batch():
    import pandas as pd
    from utd19_dss.live import LiveEngine
    eng = LiveEngine()
    eng.seek("2015-06-02", 70)
    batch = pd.read_parquet(artifacts_dir(eng.cfg) / "replay_batch.parquet")
    b = batch[(batch.day == "2015-06-02") & (batch.slot == 70)].set_index("detid")
    r = eng.window_table().set_index("detid").join(b[["priority_score"]])
    diff = (r["score"] - r["priority_score"]).abs()
    assert np.nanmax(diff.to_numpy()) < 0.11
    assert (r["score"].isna() == r["priority_score"].isna()).all()


def test_select_thresholds_f1_f2():
    sweep = [
        {"threshold": 20, "f1": 0.40, "f2": 0.60},
        {"threshold": 25, "f1": 0.50, "f2": 0.62},
        {"threshold": 35, "f1": 0.59, "f2": 0.55},
        {"threshold": 45, "f1": 0.55, "f2": 0.45},
    ]
    assert S.select_thresholds(sweep, {"high": "f1", "medium": "f2"}) == {"high": 35, "medium": 25}


def test_threshold_sweep_recall_split():
    score = np.array([[90, 10], [40, 5]], dtype=np.float32)
    target = np.array([[1, 1], [1, 0]], dtype=np.float32)
    now = np.array([[1, 0], [0, 0]], dtype=np.float32)
    r = {x["threshold"]: x for x in S.threshold_sweep(score, target, now, lo=35, hi=50, step=15)}
    assert r[35]["precision"] == 1.0 and r[35]["recall"] == pytest.approx(2 / 3, abs=1e-3)
    assert r[50]["recall_now"] == 1.0 and r[50]["recall_future"] == 0.0


@pytest.mark.skipif(not (artifacts_dir(load_config()) / "valid_scores.npz").exists(), reason="chưa chạy build")
def test_evaluate_writes_report(tmp_path, monkeypatch):
    from utd19_dss import evaluate as EV
    monkeypatch.setattr(EV, "BASE_DIR", tmp_path)
    res = EV.run()
    assert (tmp_path / "reports" / "dss_evaluation.md").exists()
    by = {r["strategy"].split(" — ")[0]: r for r in res["strategies"]}
    v5, v4 = res["strategies"][0], by["v4"]
    assert v5["f1_high"] > v4["f1_high"]
    assert v5["high_per_window_max"] <= max(res["thresholds"].get("max_high") or 10**6, 0)   # giới hạn năng lực ca trực


def test_capacity_cap_demotes_overflow():
    s = np.array([[90, 80, 70, 10, np.nan], [40, 50, 60, 70, 80]], dtype=np.float32)
    th = {"high": 35, "medium": 25, "max_high": 2}
    lv = S.level(s, th)
    assert (lv == "Cao").sum(1).tolist() == [2, 2]
    assert lv[1, 0] == "Trung bình" and lv[1, 4] == "Cao"
    assert S.overflow(s, th).sum() == 4
    assert (S.level(s, {"high": 35, "medium": 25}) == "Cao").sum() == 8


def test_goal_seek_picks_threshold():
    from utd19_dss import scoring as S
    rng = np.random.default_rng(0)
    score = rng.uniform(0, 100, (200, 20)).astype(np.float32)
    target = (score + rng.normal(0, 15, score.shape) > 70).astype(np.float32)
    curve = S.threshold_curve(score, target)
    p = S.goal_seek(curve, "precision", 0.8)
    assert p is not None and p["precision"] >= 0.8
    assert all(r["precision"] is None or r["precision"] < 0.8 for r in curve if r["threshold"] < p["threshold"])
    r = S.goal_seek(curve, "recall", 0.5)
    assert r["recall"] >= 0.5
    a = S.goal_seek(curve, "alerts", 3)
    assert a["alerts_p95"] <= 3
    assert S.goal_seek(curve, "precision", 1.01) is None


def test_decision_table_matches_action_codes():
    assert [r["rule"] for r in S.DECISION_TABLE] == list(range(1, len(S.DECISION_TABLE) + 1))
    assert {r["code"] for r in S.DECISION_TABLE} == set(S.ACTION_CODES)
