import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import gzip
import hashlib
from pathlib import Path
from collections import defaultdict
import pandas as pd
from utd19_dw.config import settings

class SourceProfiler:
    def __init__(self, data_dir: Path = None, output_dir: Path = None):
        self.data_dir = data_dir or settings.RAW_DATA_DIR
        self.output_dir = output_dir or settings.EXPORT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size = 500_000

    def _count_lines(self, filepath: Path) -> int:
        count = 0
        try:
            is_gz = filepath.name.lower().endswith(".gz")
            open_fn = gzip.open if is_gz else open
            with open_fn(filepath, "rb") as f:
                for _ in f:
                    count += 1
            return max(0, count - 1)  # Bỏ dòng header
        except Exception:
            return 0

    def run_survey(self):
        print("=== BẮT ĐẦU SẢNG LỌC VÀ SURVEY NGUỒN DỮ LIỆU (LUZERN THÁNG 1-6) ===")
        
        if not self.data_dir.exists():
            print(f"Thư mục nguồn {self.data_dir} chưa tồn tại. Tạo thư mục...")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            return

        # 1. Quét danh sách file CSV và CSV.GZ
        all_files = sorted([
            p for p in self.data_dir.rglob("*") 
            if not p.name.startswith(".") and p.name.lower().endswith((".csv", ".csv.gz"))
        ])
        
        if not all_files:
            print(f"Không tìm thấy file CSV/CSV.GZ nào trong {self.data_dir}.")
            return

        inventory_rows = []
        for p in all_files:
            try:
                hdr = pd.read_csv(p, nrows=0).columns.tolist()
            except Exception:
                hdr = []
            hdr_str = ", ".join(map(str, hdr))
            
            # Phân loại role an toàn
            cols_set = {str(c).lower().strip() for c in hdr}
            role = "other"
            fname = p.name.lower()
            if {"detid", "interval", "flow"}.issubset(cols_set) or "utd19_u" in fname or "measurements" in fname or "window_15min" in fname:
                role = "measurements"
            elif {"linkid", "order", "piece"}.issubset(cols_set) or "links" in fname:
                role = "links"
            elif ({"detid"}.issubset(cols_set) and any(k in cols_set for k in ["lanes", "pos", "fclass", "citycode"])) or "detectors" in fname or "location_profile" in fname:
                role = "detectors"

            inventory_rows.append({
                "file_name": p.name,
                "relative_path": str(p.relative_to(self.data_dir)),
                "role": role,
                "file_size_mb": round(p.stat().st_size / (1024**2), 2),
                "n_columns": len(hdr),
                "header_hash": hashlib.md5(hdr_str.encode()).hexdigest()[:10],
                "n_rows": self._count_lines(p)
            })

        df_inventory = pd.DataFrame(inventory_rows)
        df_inventory.to_csv(self.output_dir / "01_source_inventory.csv", index=False, encoding="utf-8-sig")
        print(f"-> Đã xuất: {self.output_dir / '01_source_inventory.csv'}")

        # 2. Thống kê riêng cho thành phố Luzern từ Tháng 1 -> Tháng 6
        meas_files = df_inventory[df_inventory["role"] == "measurements"]
        if not meas_files.empty:
            meas_path = self.data_dir / meas_files.iloc[0]["relative_path"]
            city_stats = defaultdict(lambda: {"rows": 0, "days": set(), "detectors": set(), "errors": 0})

            target_city = "luzern"
            allowed_months = [1, 2, 3, 4, 5, 6]

            try:
                for chunk in pd.read_csv(meas_path, chunksize=self.chunk_size, dtype=str):
                    chunk.columns = [str(c).lower().strip() for c in chunk.columns]
                    
                    # Fallback nếu thiếu cột city
                    if "city" not in chunk.columns:
                        if "citycode" in chunk.columns:
                            chunk["city"] = chunk["citycode"]
                        else:
                            chunk["city"] = target_city

                    chunk["city"] = chunk["city"].astype(str).str.lower().replace({"losanageles": "losangeles"})

                    # ---- LỌC CHỈ LẤY LUZERN ----
                    chunk = chunk[chunk["city"] == target_city].copy()
                    if chunk.empty:
                        continue

                    # ---- LỌC THÁNG 1 -> THÁNG 6 ----
                    if "day" in chunk.columns:
                        chunk["day_dt"] = pd.to_datetime(chunk["day"], format="mixed", errors="coerce")
                        chunk = chunk[chunk["day_dt"].dt.month.isin(allowed_months)].copy()
                        if chunk.empty:
                            continue

                    for city, grp in chunk.groupby("city"):
                        st = city_stats[city]
                        st["rows"] += len(grp)
                        if "day" in grp.columns:
                            st["days"].update(grp["day"].dropna().unique())
                        if "detid" in grp.columns:
                            st["detectors"].update(grp["detid"].dropna().unique())
                        if "error" in grp.columns:
                            err_mask = grp["error"].notna() & (grp["error"].str.strip() != "") & (grp["error"] != "0")
                            st["errors"] += int(err_mask.sum())

                summary_rows = []
                for city, st in city_stats.items():
                    summary_rows.append({
                        "city": city,
                        "n_detectors": len(st["detectors"]),
                        "n_days": len(st["days"]),
                        "n_weeks": round(len(st["days"]) / 7.0, 1),
                        "n_rows": st["rows"],
                        "error_pct": round(100.0 * st["errors"] / st["rows"], 2) if st["rows"] > 0 else 0.0
                    })
                
                df_summary = pd.DataFrame(summary_rows).sort_values("n_rows", ascending=False)
                df_summary.to_csv(self.output_dir / "02_city_profile.csv", index=False, encoding="utf-8-sig")
                print(f"-> Đã xuất: {self.output_dir / '02_city_profile.csv'}")
            except Exception as e:
                print(f"Lỗi khi profile file measurements: {e}")

def run_profiling():
    profiler = SourceProfiler()
    profiler.run_survey()

if __name__ == "__main__":
    run_profiling()