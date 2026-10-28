import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import contextlib
import os
import time
from pathlib import Path
import duckdb
from utd19_dw.config import settings

class DBManager:
    def __init__(self, db_path=None):
        self.db_path = db_path or settings.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(self.db_path))
        self._init_pragmas()

    def _init_pragmas(self):
        mem_limit = os.environ.get("UTD_MEMORY_LIMIT", "4GB")
        self.con.execute(f"PRAGMA memory_limit='{mem_limit}'")
        tmp_dir = settings.WORK_DIR / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        self.con.execute(f"SET temp_directory='{tmp_dir.as_posix()}'")
        self.con.execute("SET preserve_insertion_order=true")

    def execute(self, sql: str, params=None):
        if params:
            return self.con.execute(sql, params)
        return self.con.execute(sql)

    def query(self, sql: str):
        return self.con.execute(sql).df()

    def count(self, table_name: str) -> int:
        try:
            return self.con.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0]
        except Exception:
            return None

    @contextlib.contextmanager
    def step(self, name: str, table: str = None, note: str = ""):
        t0 = time.time()
        print(f"{name} ...", end=" ", flush=True)
        try:
            yield
        except Exception as e:
            sec = round(time.time() - t0, 2)
            print("ERROR")
            try:
                self.con.execute(
                    "INSERT INTO etl.run_log VALUES (?, ?, ?, ?, now())",
                    [name, sec, None, f"FAILED: {str(e)[:250]}"]
                )
            except Exception:
                pass
            raise e

        sec = round(time.time() - t0, 2)
        n_rows = self.count(table) if table else None
        
        try:
            self.con.execute(
                "INSERT INTO etl.run_log VALUES (?, ?, ?, ?, now())",
                [name, sec, n_rows, note]
            )
        except Exception:
            pass
        print(f"done ({sec}s" + (f", {n_rows:,} rows" if n_rows is not None else "") + ")")

db = DBManager()
