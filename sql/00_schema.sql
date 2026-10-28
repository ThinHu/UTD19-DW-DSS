-- Khởi tạo Schemas
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS clean;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS etl;

-- Bảng nhật ký chạy pipeline
CREATE OR REPLACE TABLE etl.run_log (
    step VARCHAR,
    seconds DOUBLE,
    rows_out BIGINT,
    note VARCHAR,
    logged_at TIMESTAMP
);

-- Bảng chứa dòng bị cách ly
CREATE OR REPLACE TABLE etl.quarantine (
    source VARCHAR,
    rule_id VARCHAR,
    city VARCHAR,
    entity_id VARCHAR,
    day VARCHAR,
    interval_value DOUBLE,
    row_id BIGINT,
    detail VARCHAR
);