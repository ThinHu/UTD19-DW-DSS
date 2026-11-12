"""Tải thời tiết theo ngày ở Luzern (nguồn ngoài cho kho dữ liệu) từ Open-Meteo Historical Weather API.

    python -m utd19_dw.weather            # → data/raw/external/weather_luzern_daily.csv
    python -m utd19_dw.pipeline           # chạy lại ETL để nạp vào dw.dim_weather

Open-Meteo miễn phí, không cần khóa API (dữ liệu tái phân tích ERA5, giấy phép CC BY 4.0).
Tệp gồm các cột: date, temperature_2m_mean (°C), precipitation_sum (mm), snowfall_sum (cm), precipitation_hours (h).
"""
from __future__ import annotations

import csv
import json
import sys
import urllib.parse
import urllib.request

from utd19_dw.config import settings

LAT, LON = 47.0502, 8.3093          # trung tâm Luzern
DAILY = ["temperature_2m_mean", "precipitation_sum", "snowfall_sum", "precipitation_hours"]
URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch(start: str, end: str) -> dict:
    q = urllib.parse.urlencode({"latitude": LAT, "longitude": LON, "start_date": start, "end_date": end,
                                "daily": ",".join(DAILY), "timezone": "Europe/Zurich"})
    with urllib.request.urlopen(f"{URL}?{q}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    start, end = settings.START_DATE, settings.END_DATE
    try:
        data = fetch(start, end)["daily"]
    except Exception as exc:  # mạng bị chặn, API lỗi...
        print(f"Không tải được thời tiết từ Open-Meteo: {exc}")
        print("Có thể tải thủ công trên trình duyệt rồi lưu thành CSV cùng cột tại:", settings.WEATHER_CSV)
        return 1
    out = settings.WEATHER_CSV
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date"] + DAILY)
        for i, d in enumerate(data["time"]):
            w.writerow([d] + [data[k][i] for k in DAILY])
    print(f"Đã lưu {len(data['time'])} ngày ({start} → {end}) vào {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
