"""Đánh giá correctness, chất lượng và query performance; DW nguồn luôn read-only."""
import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from utd19_dw.config import settings
from utd19_dw.validate import validate_database


def records(con, sql, params=None):
    cursor = con.execute(sql, params) if params is not None else con.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def percent(numerator, denominator):
    return round(100 * numerator / denominator, 4) if denominator else None


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def quality_profile(con, mode):
    load = con.execute("SELECT date_start,date_end FROM etl.load_info").fetchone()
    bounds = con.execute("SELECT min(d.full_date),max(d.full_date) FROM dw.fact_traffic_15min f JOIN dw.dim_date d USING(date_key)").fetchone()
    start = date.fromisoformat(load[0]) if load[0] not in (None, 'None') else bounds[0]
    end = date.fromisoformat(load[1]) if load[1] not in (None, 'None') else bounds[1]
    days = (end - start).days + 1 if start and end else 0
    summary = records(con, """SELECT count(*) AS windows, count(DISTINCT detector_key) AS observed_detectors,
        sum(n_intervals) AS intervals, sum(n_err) AS error_intervals,
        sum(n_flow) AS flow_present, sum(n_occ) AS occupancy_present,
        sum(n_flow_clean) AS flow_clean, sum(n_occ_clean) AS occupancy_clean
        FROM dw.fact_traffic_15min""")[0]
    summary = {key: value or 0 for key, value in summary.items()}
    roster = records(con, """SELECT count(*) AS detectors, count(*) FILTER (WHERE is_inferred) AS inferred,
        count(*) FILTER (WHERE has_location_issue) AS location_issues,
        count(*) FILTER (WHERE has_geometry_attr_issue) AS geometry_issues,
        count(*) FILTER (WHERE NOT is_link_matched) AS unmatched_links
        FROM dw.dim_detector WHERE detector_key>0""")[0]
    valid = con.execute("SELECT coalesce(sum(n_valid_windows),0) FROM mart.detector_day_15min").fetchone()[0]
    expected_windows = summary['observed_detectors'] * days * 96
    expected_intervals = summary['observed_detectors'] * days * 480
    summary.update({
        'period_start': str(start), 'period_end': str(end), 'calendar_days': days,
        'expected_windows_observed_roster': expected_windows,
        'expected_intervals_observed_roster': expected_intervals,
        'valid_windows': valid,
        'interval_coverage_pct': percent(summary['intervals'], expected_intervals),
        'window_presence_pct': percent(summary['windows'], expected_windows),
        'valid_windows_present_pct': percent(valid, summary['windows']),
        'valid_windows_expected_pct': percent(valid, expected_windows),
        'sensor_error_pct': percent(summary['error_intervals'] or 0, summary['intervals']),
        'flow_missing_pct': percent(summary['intervals'] - (summary['flow_present'] or 0), summary['intervals']),
        'occupancy_missing_pct': percent(summary['intervals'] - (summary['occupancy_present'] or 0), summary['intervals']),
    })
    source = 'measurements' if mode == 'full_3min' else 'window_15min'
    staging = 'stg.measurements_raw' if mode == 'full_3min' else 'stg.window_15min_raw'
    staged = con.execute(f'SELECT count(*) FROM {staging}').fetchone()[0]
    rejected = con.execute('SELECT count(*) FROM etl.quarantine WHERE source=?', [source]).fetchone()[0]
    monthly = records(con, """SELECT d.year_month AS month, count(*) AS windows,
        sum(f.n_intervals) AS intervals, sum(f.n_err) AS error_intervals,
        round(100.0*sum(f.n_err)/nullif(sum(f.n_intervals),0),4) AS error_pct,
        round(sum(f.sum_flow_clean)/nullif(sum(f.n_flow_clean),0),4) AS weighted_flow,
        round(sum(f.sum_occ_clean)/nullif(sum(f.n_occ_clean),0),6) AS weighted_occupancy
        FROM dw.fact_traffic_15min f JOIN dw.dim_date d USING(date_key) GROUP BY 1 ORDER BY 1""")
    detectors = records(con, """SELECT d.detid, count(*) AS windows,
        sum(f.n_intervals) AS intervals, sum(f.n_err) AS errors,
        round(100.0*sum(f.n_err)/nullif(sum(f.n_intervals),0),4) AS error_pct,
        round(100.0*sum(f.n_intervals)/nullif(? * 480,0),4) AS interval_coverage_pct
        FROM dw.fact_traffic_15min f JOIN dw.dim_detector d USING(detector_key)
        GROUP BY 1 ORDER BY error_pct DESC, d.detid LIMIT 15""", [days])
    flags = []
    if mode == 'full_3min':
        total = summary['intervals']
        for rule in settings.dq_rules:
            if rule['id'] not in {'RULE_NULL_FLOW', 'RULE_NEGATIVE_FLOW', 'RULE_FLOW_MAX', 'RULE_OCC_OOR', 'RULE_NONFINITE', 'RULE_DUPLICATE'}:
                continue
            n = con.execute('SELECT count(*) FROM dw.fact_traffic_measurement WHERE (dq_flag & ?) <> 0', [rule['bit_value']]).fetchone()[0]
            flags.append({'rule_id': rule['id'], 'rows': n, 'pct_of_fact': percent(n, total)})
    return {'summary': summary, 'roster': roster,
            'staged_rows': staged, 'rejected_rows': rejected, 'quarantine_pct': percent(rejected, staged),
            'monthly': monthly, 'worst_detectors_by_error': detectors, 'flag_counts': flags,
            'denominator_note': 'Coverage dùng detector từng có số đo × toàn bộ ngày cấu hình; không suy ra lịch vận hành cảm biến. Flag có thể chồng lấp. Quarantine dùng staging đã lọc city/ngày, không dùng toàn bộ CSV.'}


def workload(con, mode):
    detector = con.execute('SELECT detector_key FROM dw.fact_traffic_15min GROUP BY 1 ORDER BY count(*) DESC,1 LIMIT 1').fetchone()[0]
    day = con.execute('SELECT max(date_key) FROM dw.fact_traffic_15min WHERE detector_key=?', [detector]).fetchone()[0]
    month = day // 100
    return [
        {'id': 'Q1', 'name': 'Tra cứu detector/ngày', 'params': [detector, day],
         'sql': 'SELECT slot_key,n_intervals,n_err,sum_flow_clean/nullif(n_flow_clean,0) AS flow FROM dw.fact_traffic_15min WHERE detector_key=? AND date_key=? ORDER BY slot_key'},
        {'id': 'Q2', 'name': 'Tổng hợp ngày từ fact 15 phút', 'params': [],
         'sql': 'SELECT date_key,sum(sum_flow_clean)/nullif(sum(n_flow_clean),0) AS flow,sum(sum_occ_clean)/nullif(sum(n_occ_clean),0) AS occupancy FROM dw.fact_traffic_15min GROUP BY 1 ORDER BY 1'},
        {'id': 'Q3', 'name': 'Join chiều và rollup tháng/loại đường', 'params': [],
         'sql': 'SELECT dd.year_month,rc.road_group,sum(f.sum_flow_clean)/nullif(sum(f.n_flow_clean),0) AS flow FROM dw.fact_traffic_15min f JOIN dw.dim_detector d USING(detector_key) JOIN dw.dim_date dd USING(date_key) JOIN dw.dim_road_class rc USING(road_class_key) GROUP BY 1,2 ORDER BY 1,2'},
        {'id': 'Q4', 'name': 'Cửa sổ DSS toàn thành phố', 'params': [str(date(day//10000,day//100%100,day%100))],
         'sql': 'SELECT detid,n,n_err,mean_occ_clean,mean_flow_clean FROM mart.dss_detector_window WHERE day=? AND slot=48 ORDER BY detid'},
        {'id': 'Q5', 'name': 'DQ theo tháng', 'params': [],
         'sql': 'SELECT d.year_month,sum(s.n_valid_windows) AS valid_windows,sum(s.n_windows) AS windows FROM mart.detector_day_15min s JOIN dw.dim_date d USING(date_key) GROUP BY 1 ORDER BY 1'},
        {'id': 'Q8', 'name': 'View cùng tập kết quả, lọc khoảng date_key', 'params': [month*100+1, month*100+31, detector],
         'sql': 'SELECT date_key,slot_key,mean_flow_clean FROM dw.v_traffic_15min WHERE date_key BETWEEN ? AND ? AND detector_key=? ORDER BY date_key,slot_key'},
        {'id': 'Q6', 'name': 'View theo tháng/detector', 'params': [month, detector],
         'sql': 'SELECT date_key,slot_key,mean_flow_clean FROM dw.v_traffic_15min WHERE date_key//100=? AND detector_key=? ORDER BY date_key,slot_key'},
    ] + ([{'id': 'Q7', 'name': 'Tổng hợp ngày từ fact 3 phút', 'params': [],
           'sql': 'SELECT date_key,avg(flow_veh_h_lane) FILTER(WHERE coalesce(error_flag,0)=0) AS flow,avg(occupancy) FILTER(WHERE coalesce(error_flag,0)=0) AS occupancy FROM dw.fact_traffic_measurement GROUP BY 1 ORDER BY 1'}] if mode == 'full_3min' else [])


def results_match(actual, expected):
    """Cho phép sai số thứ tự cộng số thực giữa các lượt chạy song song."""
    if len(actual) != len(expected):
        return False
    for left, right in zip(actual, expected):
        if len(left) != len(right):
            return False
        for a, b in zip(left, right):
            if isinstance(a, float) and isinstance(b, float):
                if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9):
                    return False
            elif a != b:
                return False
    return True


def benchmark(con, jobs, repeats):
    results = []
    for job in jobs:
        first = time.perf_counter()
        baseline = con.execute(job['sql'], job['params']).fetchall()
        first_ms = (time.perf_counter() - first) * 1000
        samples = []
        for _ in range(repeats):
            start = time.perf_counter()
            rows = con.execute(job['sql'], job['params']).fetchall()
            samples.append((time.perf_counter() - start) * 1000)
            if not results_match(rows, baseline):
                raise RuntimeError(f"Truy vấn {job['id']} cho kết quả không ổn định")
        plan = con.execute('EXPLAIN ANALYZE ' + job['sql'], job['params']).fetchall()
        results.append({**job, 'rows_returned': len(baseline),
                        'result_sha256': hashlib.sha256(repr(baseline).encode()).hexdigest(),
                        'first_observed_ms': first_ms, 'samples_ms': samples,
                        'median_ms': statistics.median(samples), 'p95_ms': percentile(samples, .95),
                        'min_ms': min(samples), 'max_ms': max(samples),
                        'explain_analyze': '\n'.join(str(row[-1]) for row in plan)})
    return results


def index_experiment(con, point_query, repeats):
    """A/B tuần tự trên cùng bản sao tạm; không tạo index trong DW nguồn."""
    start = time.perf_counter()
    con.execute('CREATE TEMP TABLE perf_fact15 AS SELECT * FROM dw.fact_traffic_15min')
    copy_ms = (time.perf_counter()-start)*1000
    query = {**point_query, 'sql': point_query['sql'].replace('dw.fact_traffic_15min', 'perf_fact15')}
    before = benchmark(con, [query], repeats)[0]
    start = time.perf_counter()
    con.execute('CREATE INDEX perf_detector_date_idx ON perf_fact15(detector_key,date_key)')
    build_ms = (time.perf_counter()-start)*1000
    after = benchmark(con, [query], repeats)[0]
    # Một lần chạy trước/sau có thể chịu ảnh hưởng cache; EXPLAIN xác nhận index có được dùng hay không.
    con.execute('DROP TABLE perf_fact15')
    return {'candidate': 'INDEX(detector_key,date_key)', 'table': 'bản sao TEMP của toàn bộ fact 15 phút',
            'copy_ms': copy_ms, 'build_ms': build_ms, 'before': before, 'after': after,
            'same_results': before['result_sha256']==after['result_sha256'],
            'median_ratio_before_after': before['median_ms']/after['median_ms'],
            'index_scan_observed': 'index scan' in after['explain_analyze'].lower(),
            'limitation': 'Một thứ tự before→after trên bảng tạm, không phải cold-cache/concurrent benchmark; chi phí RAM/index và tốc độ ETL chưa được benchmark.'}


def compare_rollups(con):
    rows = records(con, """WITH original AS (
        SELECT date_key, avg(flow_veh_h_lane) FILTER(WHERE coalesce(error_flag,0)=0) AS flow,
        avg(occupancy) FILTER(WHERE coalesce(error_flag,0)=0) AS occ
        FROM dw.fact_traffic_measurement GROUP BY 1
    ), aggregate_fact AS (
        SELECT date_key,sum(sum_flow_clean)/nullif(sum(n_flow_clean),0) AS flow,
        sum(sum_occ_clean)/nullif(sum(n_occ_clean),0) AS occ
        FROM dw.fact_traffic_15min GROUP BY 1
    ) SELECT count(*) AS dates_compared,
        count(*) FILTER(WHERE a.date_key IS NULL OR b.date_key IS NULL
          OR (a.flow IS NULL)<>(b.flow IS NULL) OR (a.occ IS NULL)<>(b.occ IS NULL)
          OR abs(a.flow-b.flow)>1e-6 OR abs(a.occ-b.occ)>1e-8) AS differences,
        max(abs(a.flow-b.flow)) AS max_flow_error, max(abs(a.occ-b.occ)) AS max_occupancy_error
    FROM original a FULL OUTER JOIN aggregate_fact b USING(date_key)""")[0]
    return rows


def assess_database(db_path=None, repeats=10, threads=None):
    if repeats < 3:
        raise ValueError('repeats phải >= 3')
    path = Path(db_path or settings.DB_PATH).resolve()
    validation = validate_database(path)
    with tempfile.TemporaryDirectory(prefix='utd19_assess_') as scratch, duckdb.connect(str(path), read_only=True) as con:
        con.execute('SET threads=?', [threads or settings.DUCKDB_THREADS])
        con.execute('SET memory_limit=?', [os.environ.get('UTD_MEMORY_LIMIT', settings.DUCKDB_MEMORY)])
        con.execute('SET temp_directory=?', [scratch])
        quality = quality_profile(con, validation['mode'])
        jobs = sorted(workload(con, validation['mode']), key=lambda job: job['id']) if quality['summary']['windows'] else []
        timing = benchmark(con, jobs, repeats)
        by_job = {job['id']: job for job in jobs}
        rewrite_equal = results_match(con.execute(by_job['Q6']['sql'], by_job['Q6']['params']).fetchall(),
                                      con.execute(by_job['Q8']['sql'], by_job['Q8']['params']).fetchall()) if jobs else None
        experiment = index_experiment(con, by_job['Q1'], repeats) if jobs else None
        comparison = compare_rollups(con) if validation['mode'] == 'full_3min' else None
        indexes = records(con, "SELECT schema_name,table_name,index_name,is_unique,expressions FROM duckdb_indexes() WHERE schema_name='dw' ORDER BY 1,2,3")
        run = records(con, "SELECT run_id,mode,status,epoch(finished_at-started_at) AS elapsed_seconds FROM etl.runs WHERE status='SUCCESS' ORDER BY finished_at DESC LIMIT 1")
        steps = records(con, 'SELECT step,seconds,rows_out FROM etl.run_log WHERE run_id=? ORDER BY seconds DESC', [run[0]['run_id']]) if run else []
        config = dict(con.execute("SELECT name,value FROM duckdb_settings() WHERE name IN ('threads','memory_limit')").fetchall())
    status = validation['status']
    if (comparison and comparison['differences']) or rewrite_equal is False or (experiment and not experiment['same_results']):
        status = 'FAIL'
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'database': str(path),
            'status': status, 'environment': {'python': platform.python_version(), 'duckdb': duckdb.__version__,
            'os': platform.platform(), 'cpu': platform.processor(), 'logical_cpus': os.cpu_count(),
            'database_bytes': path.stat().st_size, **config},
            'methodology': {'repeats': repeats, 'warmup_queries_per_job': 1,
             'timed_scope': 'execute + fetchall; connection setup, EXPLAIN ANALYZE và validation nằm ngoài thời gian đo',
             'cache': 'warm/repeated, không xóa cache hệ điều hành; first_observed không phải cold start',
             'concurrency': 'một client, các truy vấn chạy tuần tự',
             'percentiles': 'p95 nội suy tuyến tính trên mẫu của một truy vấn; không phải SLA production'},
            'validation': validation, 'quality': quality, 'benchmarks': timing,
            'daily_rollup_comparison': comparison, 'indexes': indexes,
            'index_experiment': experiment, 'rewrite_same_results': rewrite_equal,
            'quality_status': 'MEASURED_NO_ACCEPTANCE_THRESHOLD',
            'performance_status': 'MEASURED_NO_SLA',
            'latest_successful_etl': run[0] if run else None, 'etl_steps': steps}


def markdown_report(report):
    quality = report['quality']
    s = quality['summary']
    env = report['environment']
    checks = report['validation']['checks']
    lines = ['# Đánh giá ETL/DW, Data Quality và Query Performance', '',
             f"Thời điểm (UTC): {report['checked_at']}", '',
             f"DW: `{report['database']}`. Chế độ: `{report['validation']['mode']}`.", '',
             '## Correctness và reconciliation', '',
             f"Correctness: **{report['status']}**; DQ được mô tả riêng, chưa đặt ngưỡng chấp nhận; performance chưa có SLA.  {sum(c['status']=='PASS' for c in checks)}/{len(checks)} checks PASS.", '',
             '| Bảng | Số dòng |', '|---|---:|']
    lines += [f'| {name} | {count:,} |' for name, count in report['validation']['row_counts'].items()]
    lines += ['', 'Đối soát gồm bảo toàn dòng, FK/grain/khóa chiều, clean → fact theo từng bản ghi và khóa nghiệp vụ, fact 3 → 15 phút theo từng nhóm, giá trị mart DSS và miền giá trị.', '',
              '## Data Quality', '', f"Khoảng đánh giá: {s['period_start']}–{s['period_end']} ({s['calendar_days']} ngày).", '',
              '| Chỉ tiêu | Giá trị |', '|---|---:|',
              f"| Quarantine / staging | {quality['rejected_rows']:,} / {quality['staged_rows']:,} ({quality['quarantine_pct']}%) |",
              f"| Detector có số đo | {s['observed_detectors']} |",
              f"| Độ phủ khoảng đo | {s['interval_coverage_pct']}% |",
              f"| Độ hiện diện khung 15 phút | {s['window_presence_pct']}% |",
              f"| Khung hợp lệ / khung hiện diện | {s['valid_windows_present_pct']}% |",
              f"| Khung hợp lệ / khung kỳ vọng | {s['valid_windows_expected_pct']}% |",
              f"| Khoảng đo có error_flag | {s['sensor_error_pct']}% |",
              f"| Thiếu flow sau làm sạch | {s['flow_missing_pct']}% |",
              f"| Thiếu occupancy sau làm sạch | {s['occupancy_missing_pct']}% |", '',
              quality['denominator_note'], '',
              'Khung hợp lệ theo mart.detector_day_15min: ít nhất 3 khoảng clean, mean trong miền và không thuộc trạng thái occ ≥ 0,95 với flow = 0. Đây là định nghĩa DQ của DW hiện tại.', '',
              '### Theo tháng', '', '| Tháng | Khoảng đo | Lỗi cảm biến (%) | Flow có trọng số | Occupancy có trọng số |', '|---|---:|---:|---:|---:|']
    lines += [f"| {m['month']} | {m['intervals']:,} | {m['error_pct']} | {m['weighted_flow']} | {m['weighted_occupancy']} |" for m in quality['monthly']]
    lines += ['', '### Cờ DQ thực sự được gán trên fact 3 phút', '', '| Rule | Số dòng | % fact |', '|---|---:|---:|']
    lines += [f"| {r['rule_id']} | {r['rows']:,} | {r['pct_of_fact']} |" for r in quality['flag_counts']]
    lines += ['', 'Các rule quarantine không phải cờ giữ trong fact; RULE_SPEED_OOR chưa áp dụng cho nguồn này. Không diễn giải chúng là đã kiểm tra và có 0 lỗi.', '',
              '### Detector có tỷ lệ error_flag cao nhất', '',
              '| Detector | Khoảng đo | Error (%) | Coverage (%) |', '|---|---:|---:|---:|']
    lines += [f"| {d['detid']} | {d['intervals']:,} | {d['error_pct']} | {d['interval_coverage_pct']} |" for d in quality['worst_detectors_by_error']]
    lines += ['', f"Hồ sơ detector: `{json.dumps(quality['roster'], ensure_ascii=False)}`.", '',
              '## Hiệu năng truy vấn', '',
              f"Python {env['python']}; DuckDB {env['duckdb']}; {env['os']}; threads={env['threads']}; memory_limit={env['memory_limit']}; DB={env['database_bytes']/1024**2:.1f} MiB.", '',
              f"Mỗi truy vấn có 1 lượt đầu rồi {report['methodology']['repeats']} lượt đo tuần tự; đo execute + fetchall. Đây là warm-cache, một client; chưa đo tải đồng thời hoặc cold-cache. p95 dùng nội suy tuyến tính; mẫu nhỏ chỉ mang tính mô tả.", '',
              '| Query | Nội dung | Dòng trả về | Median (ms) | p95 (ms) |', '|---|---|---:|---:|---:|']
    lines += [f"| {b['id']} | {b['name']} | {b['rows_returned']} | {b['median_ms']:.3f} | {b['p95_ms']:.3f} |" for b in report['benchmarks']]
    by_id = {b['id']: b for b in report['benchmarks']}
    if 'Q7' in by_id:
        speed = by_id['Q7']['median_ms'] / by_id['Q2']['median_ms']
        lines += ['', f"Trong lần đo này, rollup ngày từ fact 15 phút nhanh hơn fact 3 phút {speed:.2f} lần (median, Q7/Q2). Hai truy vấn dùng cùng định nghĩa error_flag=0 và mean có trọng số; đối chiếu giá trị: `{report['daily_rollup_comparison']}`."]
    if 'Q8' in by_id:
        ratio = by_id['Q6']['median_ms']/by_id['Q8']['median_ms']
        lines += ['', f"Đổi bộ lọc date_key//100 sang BETWEEN trên cột date_key: Q6/Q8={ratio:.2f} lần theo median; cùng tập kết quả: {report['rewrite_same_results']}."]
    experiment = report['index_experiment']
    if experiment:
        lines += ['', '### Thử index trên bản sao tạm', '',
                  f"Candidate: `{experiment['candidate']}`; copy table={experiment['copy_ms']:.3f}ms; build index={experiment['build_ms']:.3f}ms.", '',
                  f"Median trước/sau: {experiment['before']['median_ms']:.3f}/{experiment['after']['median_ms']:.3f}ms; ratio={experiment['median_ratio_before_after']:.2f}; index scan quan sát được: {experiment['index_scan_observed']}; kết quả giống nhau: {experiment['same_results']}.", '',
                  experiment['limitation'], '',
                  'Kết quả này chưa đủ để thêm index fact mặc định; phải xét plan và nhiều workload, không chỉ một lần đo thời gian.']
    if report['latest_successful_etl']:
        lines += ['', f"Lần ETL thành công gần nhất: {report['latest_successful_etl']['elapsed_seconds']:.3f}s (lịch sử một lần chạy, không phải benchmark nhiều lần).", '', '| Bước tốn thời gian nhất | Giây |', '|---|---:|']
        lines += [f"| {r['step']} | {r['seconds']:.3f} |" for r in report['etl_steps'][:5]]
    lines += ['', '## Nhận định và giới hạn', '',
              '- Checks PASS xác nhận các bất biến được kiểm thử; không chứng minh cảm biến đo đúng ngoài thực tế.',
              '- Tỷ lệ error_flag và độ phủ cần được xem riêng: khung hiện diện vẫn có thể không dùng được cho DSS.',
              '- Unique indexes hiện tại bảo vệ khóa dimension; thử nghiệm fact index chỉ diễn ra trên bảng tạm, DW nguồn không đổi.',
              '- Coverage giả định detector đã xuất hiện hoạt động toàn kỳ; detector mới/lịch bảo trì có thể làm tỷ lệ thấp mà không phải lỗi ETL.',
              '- SQL, tham số, từng mẫu thời gian, EXPLAIN ANALYZE và toàn bộ checks nằm trong JSON cùng tên.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Đánh giá correctness/DQ/query performance của DW')
    parser.add_argument('--db', type=Path, default=settings.DB_PATH)
    parser.add_argument('--repeats', type=int, default=10)
    parser.add_argument('--report-dir', type=Path, default=settings.BASE_DIR / 'reports')
    args = parser.parse_args()
    report = assess_database(args.db, args.repeats)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    stem = args.report_dir / 'dw_assessment'
    stem.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8')
    stem.with_suffix('.md').write_text(markdown_report(report), encoding='utf-8')
    print(f"Assessment {report['status']}: {stem.with_suffix('.md')}")
    return 0 if report['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
