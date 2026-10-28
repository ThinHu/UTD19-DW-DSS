import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()

# Tự động xác định BASE_DIR dù utd19_dw nằm ở root hay trong src/
_curr = Path(__file__).resolve().parent
if _curr.parent.name == "src":
    BASE_DIR = _curr.parent.parent
else:
    BASE_DIR = _curr.parent

CONFIG_DIR = BASE_DIR / "config"

class Settings:
    def __init__(self):
        self.BASE_DIR = BASE_DIR
        with open(CONFIG_DIR / "settings.yaml", "r", encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f)

        with open(CONFIG_DIR / "dq_rules.yaml", "r", encoding="utf-8") as f:
            self._rules = yaml.safe_load(f)["rules"]

        # Paths (chuẩn hóa resolve relative to BASE_DIR nếu là đường dẫn tương đối)
        raw_root = os.environ.get("UTD_DATA_ROOT")
        self.RAW_DATA_DIR = (BASE_DIR / raw_root).resolve() if raw_root and not Path(raw_root).is_absolute() else Path(raw_root or (BASE_DIR / "data" / "raw")).resolve()
        
        work_dir = os.environ.get("UTD_WORK_DIR")
        self.WORK_DIR = (BASE_DIR / work_dir).resolve() if work_dir and not Path(work_dir).is_absolute() else Path(work_dir or (BASE_DIR / "data" / "work")).resolve()
        
        export_dir = os.environ.get("UTD_EXPORT_DIR")
        self.EXPORT_DIR = (BASE_DIR / export_dir).resolve() if export_dir and not Path(export_dir).is_absolute() else Path(export_dir or (BASE_DIR / "data" / "export")).resolve()

        # Params
        self.CITIES = self._cfg["project"]["cities"]
        date_cfg = self._cfg["project"].get("date_range", {})
        self.START_DATE = date_cfg.get("start_date")
        self.END_DATE = date_cfg.get("end_date")

        self.DUCKDB_THREADS = self._cfg.get("duckdb", {}).get("threads", 4)
        self.DUCKDB_MEMORY = self._cfg.get("duckdb", {}).get("memory_limit", "4GB")

        self.SMOKE_ROWS = os.environ.get("UTD_SMOKE_ROWS") or self._cfg["project"]["smoke_rows"]
        if self.SMOKE_ROWS:
            self.SMOKE_ROWS = int(self.SMOKE_ROWS)
            
        self.INTERVAL_OOR_MODE = self._cfg["data_warehouse"]["interval_oor_mode"]
        self.COVERAGE_MIN = self._cfg["data_warehouse"]["coverage_min"]
        self.FLOW_MAX = self._cfg["data_warehouse"]["flow_max"]
        self.EXCLUDE_RULES_IN_MART = self._cfg["data_warehouse"]["exclude_rules_in_mart"]
        
        self.DB_PATH = self.WORK_DIR / self._cfg["paths"]["db_filename"]

    @property
    def dq_rules(self):
        return self._rules

    def get_dq_mask(self, rule_ids: list[str]) -> int:
        mask = 0
        for r in self._rules:
            if r["id"] in rule_ids:
                mask |= r["bit_value"]
        return mask

settings = Settings()
