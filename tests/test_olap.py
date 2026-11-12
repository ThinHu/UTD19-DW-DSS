"""Kiểm tra các phép tổng hợp OLAP bằng số liệu nhỏ tính tay được."""
import duckdb
import pytest

from utd19_dw.olap import OlapService


@pytest.fixture
def olap(tmp_path):
    path = tmp_path / "traffic.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA dw")
    con.execute("CREATE SCHEMA etl")
    con.execute("CREATE TABLE etl.load_info (mode VARCHAR)")
    con.execute("INSERT INTO etl.load_info VALUES ('export_15min')")
    con.execute("""CREATE TABLE dw.dim_date (date_key INTEGER, full_date DATE, year INTEGER, quarter INTEGER,
        month INTEGER, year_month VARCHAR, iso_week INTEGER, day_of_week INTEGER, day_name_vn VARCHAR,
        day_type VARCHAR, day_type_label VARCHAR)""")
    con.execute("""INSERT INTO dw.dim_date VALUES
        (20150101, '2015-01-01', 2015, 1, 1, '2015-01', 1, 4, 'Thứ 5', 'WD', 'Ngày làm việc'),
        (20150103, '2015-01-03', 2015, 1, 1, '2015-01', 1, 6, 'Thứ 7', 'SAT', 'Thứ Bảy')""")
    con.execute("""CREATE TABLE dw.dim_time_slot (slot_key INTEGER, hour INTEGER, hour_label VARCHAR,
        slot_label VARCHAR, daypart VARCHAR, daypart_order INTEGER, is_peak BOOLEAN)""")
    con.execute("""INSERT INTO dw.dim_time_slot VALUES
        (0, 0, '00:00–00:59', '00:00', 'Đêm', 1, FALSE),
        (1, 0, '00:00–00:59', '00:15', 'Đêm', 1, FALSE)""")
    con.execute("CREATE TABLE dw.dim_road_class (road_class_key INTEGER, road_group VARCHAR, fclass VARCHAR, fclass_description VARCHAR)")
    con.execute("INSERT INTO dw.dim_road_class VALUES (1, 'Trục chính', 'primary', 'Đường chính'), (2, 'Đường gom', 'tertiary', 'Đường cấp 3')")
    con.execute("""CREATE TABLE dw.dim_detector (detector_key INTEGER, road_class_key INTEGER, detid VARCHAR,
        road VARCHAR, lat DOUBLE, "long" DOUBLE, lanes INTEGER, speed_limit_kmh DOUBLE, is_current BOOLEAN)""")
    con.execute("""INSERT INTO dw.dim_detector VALUES
        (1, 1, 'D1', 'Road A', 47.1, 8.3, 2, 50, TRUE),
        (2, 2, 'D2', 'Road B', 47.2, 8.4, 1, 30, TRUE),
        (3, 1, 'D3', 'Road A', 47.3, 8.5, 1, 40, TRUE)""")
    con.execute("""CREATE TABLE dw.fact_traffic_15min (
        detector_key INTEGER, date_key INTEGER, slot_key INTEGER,
        n_intervals INTEGER, n_err INTEGER, n_occ_clean INTEGER, n_flow_clean INTEGER,
        sum_occ_clean DOUBLE, sum_flow_clean DOUBLE
    )""")
    con.execute("""INSERT INTO dw.fact_traffic_15min VALUES
        (1, 20150101, 0, 5, 0, 5, 5, 1.0, 500),
        (1, 20150101, 1, 5, 0, 1, 1, 0.8, 300),
        (2, 20150101, 0, 5, 1, 4, 4, 2.0, 800),
        (2, 20150103, 0, 5, 0, 4, 4, 0.4, 400)
    """)
    con.close()
    return OlapService(path)


def test_weighted_rollup_excludes_invalid_windows(olap):
    result = olap.query(period="day", road="all", start="2015-01-01", end="2015-01-01")
    row = result["rows"][0]
    assert row["observed_windows"] == 3
    assert row["valid_windows"] == 2
    assert row["avg_occupancy_pct"] == pytest.approx(33.33, abs=0.01)
    assert row["avg_flow"] == pytest.approx(144.44, abs=0.01)
    assert row["valid_coverage_pct"] == pytest.approx(66.67, abs=0.01)
    assert row["error_pct"] == pytest.approx(6.67, abs=0.01)
    assert row["valid_detectors"] == 2
    assert result["summary"]["avg_occupancy_pct"] == row["avg_occupancy_pct"]


def test_slice_and_drill_down(olap):
    assert olap.options()["start"] == "2015-01-01"
    assert olap.options()["end"] == "2015-01-03"
    assert len(olap.query(period="month", road="all")["rows"]) == 1
    assert len(olap.query(period="day", road="all")["rows"]) == 2
    rows = olap.query(period="all", road="group", day_type="WD")["rows"]
    assert {r["road_key"] for r in rows} == {"Trục chính", "Đường gom"}
    one = olap.query(period="all", road="detector", road_group="Trục chính")["rows"]
    assert [r["road_key"] for r in one] == ["D1"]
    assert olap.query(group_by="year")["rows"][0]["group_key"] == "2015"
    assert olap.query(group_by="month", year=2015)["rows"][0]["group_key"] == "2015-01"
    assert olap.query(group_by="day", year=2015, month=1)["rows"][0]["group_key"] == "2015-01-01"
    assert olap.query(group_by="hour", date_value="2015-01-01")["rows"][0]["group_key"] == "0"
    assert olap.query(group_by="slot", date_value="2015-01-01", hour=0)["rows"][0]["group_key"] == "0"
    assert olap.query(group_by="quarter", year=2015)["rows"][0]["group_key"] == "2015-Q1"
    assert olap.query(group_by="slot", daypart="Đêm", hour=0)["rows"][0]["group_key"] == "0"


def test_cross_dimensions_and_detector_context(olap):
    heat = olap.query(group_by="day_of_week", split_by="hour")
    assert {(r["group_key"], r["split_key"]) for r in heat["rows"]} == {("4", "0"), ("6", "0")}
    assert heat["summary"]["avg_occupancy_pct"] == pytest.approx(26.15, abs=0.01)
    selected = olap.query(group_by="road_group", day_of_week=4, detid="D1")
    assert [r["group_key"] for r in selected["rows"]] == ["Trục chính"]
    assert selected["summary"]["observed_windows"] == 2
    assert selected["summary"]["valid_windows"] == 1
    assert olap.query(group_by="detector", road_name="Road B")["rows"][0]["group_key"] == "D2"
    assert olap.query(group_by="detector", day_of_week=4, hour_start=0, hour_end=0)["summary"]["observed_windows"] == 3
    assert len(olap.options()["detectors"]) == 3


def test_registered_detector_denominator_includes_no_fact(olap):
    detectors = olap.options()["detectors"]
    road_detectors = [detector for detector in detectors if detector["road"] == "Road A"]
    assert {detector["detid"] for detector in road_detectors} == {"D1", "D3"}
    scoped = olap.query(group_by="detector", road_name="Road A", start="2015-01-01", end="2015-01-01")
    assert scoped["summary"]["valid_detectors"] == 1
    assert len(road_detectors) == 2
    empty_day = olap.query(group_by="detector", road_name="Road A", start="2015-01-02", end="2015-01-02")
    assert empty_day["summary"]["valid_detectors"] == 0
    assert len(road_detectors) == 2


def test_rejects_invalid_grouping_and_dates(olap):
    with pytest.raises(ValueError, match="Chiều phân tích"):
        olap.query(period="month; DROP TABLE dw.dim_date", road="all")
    with pytest.raises(ValueError, match="Chiều phân tích"):
        olap.query(group_by="day_of_week; DROP TABLE dw.dim_date")
    with pytest.raises(ValueError, match="Ngày bắt đầu"):
        olap.query(start="2015-02-01", end="2015-01-01")
    with pytest.raises(ValueError, match="Giờ bắt đầu"):
        olap.query(hour_start=9, hour_end=7)
