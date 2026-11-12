CREATE OR REPLACE TABLE clean.detectors_typed AS
SELECT row_number() OVER () AS _rn,
       lower(trim(coalesce(citycode, 'luzern'))) AS citycode,
       NULLIF(regexp_replace(trim(detid), '\.0$', ''), '') AS detid,
       TRY_CAST("length" AS DOUBLE) AS lane_length_km,
       TRY_CAST(pos AS DOUBLE) AS pos_km,
       TRY_CAST("long" AS DOUBLE) AS "long",
       TRY_CAST(lat AS DOUBLE) AS lat,
       TRY_CAST(lanes AS DOUBLE) AS lanes_raw,
       NULLIF(regexp_replace(trim(linkid), '\.0$', ''), '') AS linkid,
       NULLIF(trim(fclass), '') AS fclass,
       NULLIF(trim(road), '') AS road,
       NULLIF(trim("limit"), '') AS speed_limit_raw
FROM stg.detectors_raw;

-- Không điền tọa độ giả: thiếu hoặc lệch xa trung vị thành phố (> 0,2°, ~20 km) thì để NULL và gắn cờ.
CREATE OR REPLACE TABLE clean.detectors AS
WITH ok AS (
    SELECT * FROM clean.detectors_typed
    WHERE citycode IN ({CITY_IN}) AND detid IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY citycode, detid ORDER BY _rn DESC) = 1
), m AS (
    SELECT *,
           median(lat) OVER (PARTITION BY citycode) AS mlat,
           median("long") OVER (PARTITION BY citycode) AS mlong
    FROM ok
), flag AS (
    SELECT *, (lat IS NULL OR "long" IS NULL OR abs(lat - mlat) > 0.2 OR abs("long" - mlong) > 0.2) AS bad_loc
    FROM m
)
SELECT citycode, detid,
       CASE WHEN bad_loc THEN NULL ELSE "long" END AS "long",
       CASE WHEN bad_loc THEN NULL ELSE lat END AS lat,
       linkid, fclass, road, lane_length_km, pos_km, speed_limit_raw,
       CASE WHEN lanes_raw IS NOT NULL AND lanes_raw BETWEEN 1 AND 12 THEN CAST(lanes_raw AS TINYINT) ELSE 1 END AS lanes,
       CASE WHEN TRY_CAST(speed_limit_raw AS DOUBLE) > 0 THEN TRY_CAST(speed_limit_raw AS DOUBLE) END AS speed_limit_kmh,
       bad_loc AS has_location_issue,
       (lane_length_km IS NULL OR lane_length_km <= 0) AS has_geometry_attr_issue
FROM flag;
