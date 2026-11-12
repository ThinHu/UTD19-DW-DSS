-- Chế độ nạp từ bản xuất (khi không có utd19_u.csv gốc): staging đọc bản xuất khung 15 phút của DW
-- (detector_window_15min.csv.gz) và hồ sơ detector. Các bảng staging giữ nguyên dạng chuỗi như nguồn.
CREATE OR REPLACE TABLE stg.window_15min_raw AS
SELECT row_number() OVER () AS _row_id, *
FROM read_csv('{EXPORT_SRC_DIR}/detector_window_15min.csv.gz', header = true, all_varchar = true)
WHERE TRUE AND (TRY_CAST(day AS DATE) IS NULL OR (TRUE {DATE_FILTER_SQL}))
{LIMIT_SQL};

CREATE OR REPLACE TABLE stg.detectors_raw AS
SELECT * FROM read_csv('{EXPORT_SRC_DIR}/detector_location_profile.csv', header = true, all_varchar = true);

ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "citycode" VARCHAR DEFAULT 'luzern';
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "length" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "pos" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "lanes" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "limit" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "long" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "lat" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "linkid" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "fclass" VARCHAR DEFAULT NULL;
ALTER TABLE stg.detectors_raw ADD COLUMN IF NOT EXISTS "road" VARCHAR DEFAULT NULL;

-- Bản xuất không kèm hình học link → bảng rỗng cùng cấu trúc (dim_link chỉ còn dòng 'unknown').
CREATE OR REPLACE TABLE stg.links_raw (
    citycode VARCHAR, linkid VARCHAR, "order" VARCHAR, piece VARCHAR, "group" VARCHAR, "long" VARCHAR, lat VARCHAR
);
