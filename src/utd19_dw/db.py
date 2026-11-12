"""Kết nối lười và nhật ký từng bước ETL; import không mở tệp DW."""
import contextlib
import logging
import os
import time
from pathlib import Path

import duckdb

from utd19_dw.config import settings

logger = logging.getLogger("utd19_dw")


class DBManager:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path or settings.DB_PATH)
        self._con = None
        self.run_id = None
        self.pending_logs = None

    @property
    def con(self):
        if self._con is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._con = duckdb.connect(str(self.db_path))
            try:
                self._init_pragmas()
            except Exception:
                self.close()
                raise
        return self._con

    def _init_pragmas(self):
        mem_limit = os.environ.get("UTD_MEMORY_LIMIT", settings.DUCKDB_MEMORY)
        self._con.execute("SET memory_limit = ?", [mem_limit])
        self._con.execute("SET threads = ?", [settings.DUCKDB_THREADS])
        tmp_dir = self.db_path.parent / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        self._con.execute("SET temp_directory = ?", [tmp_dir.as_posix()])
        self._con.execute("SET preserve_insertion_order = true")

    def close(self):
        if self._con is not None:
            self._con.close()
            self._con = None

    def execute(self, sql: str, params=None):
        return self.con.execute(sql, params) if params is not None else self.con.execute(sql)

    def query(self, sql: str):
        return self.execute(sql).df()

    def count(self, table_name: str):
        try:
            return self.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0]
        except duckdb.CatalogException:
            return None

    def _write_log(self, event):
        self.execute("""INSERT INTO etl.run_log
            (step, seconds, rows_out, note, logged_at, run_id, status)
            VALUES (?, ?, ?, ?, CAST(now() AS TIMESTAMP), ?, ?)""", event)

    def flush_logs(self):
        for event in self.pending_logs or []:
            self._write_log(event)
        self.pending_logs = None

    @contextlib.contextmanager
    def step(self, name: str, table: str | None = None, note: str = ""):
        t0 = time.monotonic()
        logger.info("Bắt đầu bước %s", name)
        status, rows = "SUCCESS", None
        try:
            yield
            rows = self.count(table) if table else None
        except Exception as exc:
            status, note = "FAILED", str(exc)[:4000]
            logger.exception("Bước %s thất bại", name)
            raise
        finally:
            seconds = round(time.monotonic() - t0, 3)
            event = [name, seconds, rows, note, self.run_id, status]
            if self.pending_logs is not None:
                self.pending_logs.append(event)
            else:
                self._write_log(event)
            logger.info("Kết thúc bước %s: %s, %.3fs, rows=%s", name, status, seconds, rows)


db = DBManager()
