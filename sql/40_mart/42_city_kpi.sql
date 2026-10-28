CREATE OR REPLACE TABLE mart.city_kpi AS
SELECT m.citycode, 
       count(*) AS mfd_points, 
       count(DISTINCT m.date_key) AS days, 
       round(avg(n_detectors), 1) AS avg_detectors_per_interval,
       round(quantile_cont(flow_w, 0.95), 1) AS capacity_flow_p95, 
       round(quantile_cont(occ_w, 0.95), 4) AS occ_p95,
       round(avg(flow_w), 1) AS mean_flow_w, 
       round(avg(occ_w), 4) AS mean_occ_w
FROM mart.mfd_city_interval m GROUP BY 1 ORDER BY 1;