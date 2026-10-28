import duckdb

def test_reconciliation_logic():
    con = duckdb.connect(":memory:")
    
    # 1. Setup Schemas
    con.execute("CREATE SCHEMA stg; CREATE SCHEMA clean; CREATE SCHEMA dw; CREATE SCHEMA etl;")
    
    # 2. Setup Staging & Quarantine
    con.execute("""
    CREATE TABLE stg.measurements_raw (
        city VARCHAR, day VARCHAR, interval INT, detid VARCHAR, flow DOUBLE, occ DOUBLE, speed DOUBLE, error VARCHAR
    );
    INSERT INTO stg.measurements_raw VALUES 
        ('bern', '2019-01-01', 300, 'D1', 120.0, 10.0, 50.0, ''),
        ('bern', '2019-01-01', 600, 'D1', 130.0, 12.0, 48.0, ''),
        ('bern', '2019-01-01', 999999, 'D1', 0.0, 0.0, 0.0, ''); -- Out of range
    """)
    
    con.execute("""
    CREATE TABLE etl.quarantine (
        source VARCHAR, rule_id VARCHAR, city VARCHAR, entity_id VARCHAR, day VARCHAR, interval_value DOUBLE, row_id BIGINT, detail VARCHAR
    );
    INSERT INTO etl.quarantine VALUES 
        ('measurements', 'RULE_INTERVAL_OOR', 'bern', 'D1', '2019-01-01', 999999, 1, 'Interval OOR');
    """)
    
    # 3. Setup Dimensions with Unknown Key = 0
    con.execute("""
    CREATE TABLE dw.dim_date (date_key INT, full_date DATE);
    INSERT INTO dw.dim_date VALUES (0, '1970-01-01'), (20190101, '2019-01-01');
    
    CREATE TABLE dw.dim_detector (detector_key INT, detid VARCHAR);
    INSERT INTO dw.dim_detector VALUES (0, 'unknown'), (1, 'D1');
    """)
    
    # 4. Setup Fact (2 valid rows, quarantined row excluded)
    con.execute("""
    CREATE TABLE dw.fact_traffic_measurement (
        date_key INT, city_key INT, detector_key INT, interval_seconds INT, flow DOUBLE, speed_kmh DOUBLE, occupancy DOUBLE, dq_mask INT, error_flag VARCHAR
    );
    INSERT INTO dw.fact_traffic_measurement VALUES 
        (20190101, 1, 1, 300, 120.0, 50.0, 10.0, 0, ''),
        (20190101, 1, 1, 600, 130.0, 48.0, 12.0, 0, '');
    """)
    
    # 5. Run Reconciliation Query
    con.execute("""
    CREATE TABLE etl.reconciliation AS
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
           CASE WHEN expected = actual THEN 'PASS' ELSE 'FAIL' END AS status
    FROM checks;
    """)
    
    res = con.execute("SELECT check_id, status FROM etl.reconciliation").fetchall()
    status_dict = dict(res)
    
    assert status_dict["RC-A"] == "PASS"
    assert status_dict["RC-B"] == "PASS"
    assert status_dict["RC-C"] == "PASS"
