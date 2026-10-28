CREATE OR REPLACE TABLE stg.detectors_raw AS 
SELECT * FROM read_csv('{DATA_RAW_DIR}/*detector*.csv', all_varchar=true, header=true, ignore_errors=true);

-- Tu dong bo sung cac cot neu file nguon thieu
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
