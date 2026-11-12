-- Index duy nhất trên khóa dimension: bảo vệ quan hệ join.
-- Không tạo index lớn trên fact khi chưa đo workload cụ thể.
CREATE UNIQUE INDEX IF NOT EXISTS idx_city_key ON dw.dim_city(city_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_link_key ON dw.dim_link(link_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_detector_key ON dw.dim_detector(detector_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_date_key ON dw.dim_date(date_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_slot_key ON dw.dim_time_slot(slot_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_road_class_key ON dw.dim_road_class(road_class_key);

-- Trung bình luôn tính từ sum/count; khi roll-up phải tiếp tục cộng sum và count.
CREATE OR REPLACE VIEW dw.v_traffic_15min AS
SELECT f.*, d.detid, c.citycode, dd.full_date,
       f.sum_occ_all / nullif(f.n_occ,0) AS mean_occ_all,
       f.sum_flow_all / nullif(f.n_flow,0) AS mean_flow_all,
       f.sum_occ_clean / nullif(f.n_occ_clean,0) AS mean_occ_clean,
       f.sum_flow_clean / nullif(f.n_flow_clean,0) AS mean_flow_clean
FROM dw.fact_traffic_15min f JOIN dw.dim_detector d USING(detector_key)
JOIN dw.dim_city c USING(city_key) JOIN dw.dim_date dd USING(date_key);
CREATE OR REPLACE VIEW etl.v_quality_checks AS
SELECT * FROM etl.reconciliation UNION ALL SELECT * FROM etl.validation_results;
CREATE OR REPLACE VIEW etl.v_quarantine_summary AS
SELECT source, rule_id, count(*) AS rows_rejected FROM etl.quarantine GROUP BY source, rule_id;
