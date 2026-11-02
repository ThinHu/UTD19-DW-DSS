"""Lưu kết quả chấm điểm live và nhật ký hành động vào DuckDB (schema dss)."""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS dss;
CREATE TABLE IF NOT EXISTS dss.priority_live (
    detid VARCHAR, day DATE, slot SMALLINT, window_start TIMESTAMP,
    priority_score DOUBLE, priority_level VARCHAR, top_factor VARCHAR,
    c1 DOUBLE, c2 DOUBLE, c3 DOUBLE, c4 DOUBLE, c5 DOUBLE, p_event30 DOUBLE,
    occ DOUBLE, flow DOUBLE, mu_occ DOUBLE, mu_flow DOUBLE, data_tier VARCHAR,
    scored_at TIMESTAMP
);
CREATE SEQUENCE IF NOT EXISTS dss.action_seq START 1;
CREATE TABLE IF NOT EXISTS dss.action_log (
    id BIGINT DEFAULT nextval('dss.action_seq'), created_at TIMESTAMP, window_start TIMESTAMP,
    detid VARCHAR, road VARCHAR, priority_score DOUBLE, priority_level VARCHAR,
    action_code VARCHAR, action_text VARCHAR, decision VARCHAR, note VARCHAR, operator VARCHAR
);
"""


class ResultStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        self.con.execute(SCHEMA)
        self.lock = threading.Lock()

    def clear_live(self):
        with self.lock:
            self.con.execute("DELETE FROM dss.priority_live")

    def write_windows(self, eng, a: int, b: int):
        from . import scoring as S
        frames = []
        for t in range(a, b):
            r = t - eng.t_rep0
            sc = S.priority(eng.C[r], eng.weights)
            lvl = S.level(sc, eng.thresholds)
            top = S.top_factor(eng.C[r], eng.weights)
            day, slot = eng.grid.day_of(t), t % 96
            ws = pd.Timestamp(day) + pd.Timedelta(minutes=15 * slot)
            frames.append(pd.DataFrame({
                "detid": eng.grid.detids, "day": pd.Timestamp(day).date(), "slot": slot, "window_start": ws,
                "priority_score": np.round(sc, 1), "priority_level": lvl,
                "top_factor": np.where(np.isnan(sc), "", top),
                "c1": eng.C[r, :, 0], "c2": eng.C[r, :, 1], "c3": eng.C[r, :, 2], "c4": eng.C[r, :, 3],
                "c5": eng.C[r, :, 4], "p_event30": eng.P[r], "occ": eng.grid.occ[t], "flow": eng.grid.flow[t],
                "mu_occ": eng.mu_occ[r], "mu_flow": eng.mu_flow[r], "data_tier": eng.tier,
                "scored_at": datetime.now(),
            }))
        df = pd.concat(frames, ignore_index=True)
        with self.lock:
            self.con.register("_new", df)
            self.con.execute("DELETE FROM dss.priority_live WHERE window_start IN (SELECT DISTINCT window_start FROM _new)")
            self.con.execute("INSERT INTO dss.priority_live SELECT * FROM _new")
            self.con.unregister("_new")

    def add_action(self, rec: dict) -> int:
        with self.lock:
            return self.con.execute(
                """INSERT INTO dss.action_log (created_at, window_start, detid, road, priority_score, priority_level,
                   action_code, action_text, decision, note, operator) VALUES (?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
                [datetime.now(), rec["window_start"], rec["detid"], rec.get("road"), rec.get("priority_score"),
                 rec.get("priority_level"), rec.get("action_code"), rec.get("action_text"), rec.get("decision"),
                 rec.get("note"), rec.get("operator")]).fetchone()[0]

    def actions(self) -> pd.DataFrame:
        with self.lock:
            return self.con.execute("SELECT * FROM dss.action_log ORDER BY id DESC").df()

    def query(self, sql: str, params=None) -> pd.DataFrame:
        with self.lock:
            return self.con.execute(sql, params or []).df()
