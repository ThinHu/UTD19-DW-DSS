CREATE OR REPLACE TABLE etl.reconciliation AS
WITH checks AS (
    SELECT 'RC-A' AS check_id, 'Toàn vẹn dòng Fact vs (Staging - Quarantine)' AS description,
           (SELECT count(*) FROM stg.measurements_raw) - 
           (SELECT count(*) FROM etl.quarantine WHERE source = 'measurements') AS expected,
           (SELECT count(*) FROM dw.fact_traffic_measurement) AS actual
    UNION ALL
    SELECT 'RC-B', 'Toàn vẹn Detector Keys (Không orphan)',
           0,
           (SELECT count(*) FROM dw.fact_traffic_measurement f ANTI JOIN dw.dim_detector d USING (detector_key))
    UNION ALL
    SELECT 'RC-C', 'Toàn vẹn Date Keys (Không orphan)',
           0,
           (SELECT count(*) FROM dw.fact_traffic_measurement f ANTI JOIN dw.dim_date d USING (date_key))
)
SELECT check_id, description, expected, actual,
       CASE WHEN expected = actual THEN 'PASS' ELSE 'FAIL' END AS status,
       now() AS checked_at
FROM checks;
