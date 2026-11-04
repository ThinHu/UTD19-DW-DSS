-- Khởi tạo Schemas
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS clean;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS etl;

-- Bảng nhật ký chạy pipeline
CREATE TABLE IF NOT EXISTS etl.run_log (
    step VARCHAR,
    seconds DOUBLE,
    rows_out BIGINT,
    note VARCHAR,
    logged_at TIMESTAMP
);

-- Nâng cấp nhật ký cũ mà không xóa lịch sử.
ALTER TABLE etl.run_log ADD COLUMN IF NOT EXISTS run_id VARCHAR;
ALTER TABLE etl.run_log ADD COLUMN IF NOT EXISTS status VARCHAR;
CREATE TABLE IF NOT EXISTS etl.runs (
    run_id VARCHAR PRIMARY KEY,
    mode VARCHAR, source VARCHAR, status VARCHAR,
    started_at TIMESTAMP, finished_at TIMESTAMP, error VARCHAR
);
CREATE TABLE IF NOT EXISTS etl.check_history (
    run_id VARCHAR, check_id VARCHAR, description VARCHAR,
    expected DOUBLE, actual DOUBLE, status VARCHAR, checked_at TIMESTAMP
);

-- Bảng chứa dòng bị cách ly
CREATE TABLE IF NOT EXISTS etl.quarantine (
    source VARCHAR,
    rule_id VARCHAR,
    city VARCHAR,
    entity_id VARCHAR,
    day VARCHAR,
    interval_value DOUBLE,
    row_id BIGINT,
    detail VARCHAR
);
