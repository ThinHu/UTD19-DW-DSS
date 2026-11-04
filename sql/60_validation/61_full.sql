-- Đối soát từng nhóm, không chỉ so tổng số dòng toàn kho.
INSERT INTO etl.validation_results
WITH expected_groups AS (
SELECT detector_key, date_key, CAST(time_key // 900 AS SMALLINT) AS slot_key,
count(*) AS n_intervals,
count(*) FILTER (WHERE error_flag=1) AS n_err,
count(occupancy) AS n_occ,
count(flow_veh_h_lane) AS n_flow,
count(*) FILTER (WHERE flow_veh_h_lane=0) AS n_flow0,
count(occupancy) FILTER (WHERE coalesce(error_flag,0)=0) AS n_occ_clean,
count(flow_veh_h_lane) FILTER (WHERE coalesce(error_flag,0)=0) AS n_flow_clean,
sum(occupancy) AS sum_occ_all,
sum(flow_veh_h_lane) AS sum_flow_all,
sum(occupancy) FILTER (WHERE coalesce(error_flag,0)=0) AS sum_occ_clean,
sum(flow_veh_h_lane) FILTER (WHERE coalesce(error_flag,0)=0) AS sum_flow_clean
FROM dw.fact_traffic_measurement
WHERE detector_key > 0 AND time_key >= 0 GROUP BY detector_key, date_key, time_key // 900
), differences AS (
SELECT 1 FROM expected_groups a FULL OUTER JOIN dw.fact_traffic_15min b
USING(detector_key, date_key, slot_key)
WHERE a.detector_key IS NULL OR b.detector_key IS NULL OR a.n_intervals IS DISTINCT FROM b.n_intervals OR a.n_err IS DISTINCT FROM b.n_err OR a.n_occ IS DISTINCT FROM b.n_occ OR a.n_flow IS DISTINCT FROM b.n_flow OR a.n_flow0 IS DISTINCT FROM b.n_flow0 OR a.n_occ_clean IS DISTINCT FROM b.n_occ_clean OR a.n_flow_clean IS DISTINCT FROM b.n_flow_clean OR ((a.sum_occ_all IS NULL) <> (b.sum_occ_all IS NULL) OR abs(a.sum_occ_all-b.sum_occ_all) > 1e-7 + 1e-7*abs(a.sum_occ_all)) OR ((a.sum_flow_all IS NULL) <> (b.sum_flow_all IS NULL) OR abs(a.sum_flow_all-b.sum_flow_all) > 1e-7 + 1e-7*abs(a.sum_flow_all)) OR ((a.sum_occ_clean IS NULL) <> (b.sum_occ_clean IS NULL) OR abs(a.sum_occ_clean-b.sum_occ_clean) > 1e-7 + 1e-7*abs(a.sum_occ_clean)) OR ((a.sum_flow_clean IS NULL) <> (b.sum_flow_clean IS NULL) OR abs(a.sum_flow_clean-b.sum_flow_clean) > 1e-7 + 1e-7*abs(a.sum_flow_clean))
)
SELECT 'DQ-ROLLUP', 'Fact 15 phút khớp mọi sum/count theo từng nhóm từ fact 3 phút',
0, count(*), CASE WHEN count(*)=0 THEN 'PASS' ELSE 'FAIL' END, CAST(now() AS TIMESTAMP)
FROM differences;
