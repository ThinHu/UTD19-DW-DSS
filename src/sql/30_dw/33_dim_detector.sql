CREATE OR REPLACE TABLE dw.dim_detector AS
WITH src AS (
    SELECT d.citycode, d.detid, d."long", d.lat, d.lanes, d.lane_length_km, d.pos_km, d.road, d.speed_limit_kmh, d.linkid, d.fclass,
           d.has_location_issue, d.has_geometry_attr_issue, FALSE AS is_inferred
    FROM clean.detectors d
    UNION ALL BY NAME
    SELECT DISTINCT m.city AS citycode, m.detid, CAST(NULL AS DOUBLE) AS "long", CAST(NULL AS DOUBLE) AS lat, 1 AS lanes, NULL AS lane_length_km, NULL AS pos_km, NULL AS road, NULL AS speed_limit_kmh, NULL AS linkid, NULL AS fclass,
           TRUE AS has_location_issue, TRUE AS has_geometry_attr_issue, TRUE AS is_inferred
    FROM clean.measurements m WHERE NOT EXISTS (SELECT 1 FROM clean.detectors d WHERE d.citycode = m.city AND d.detid = m.detid)
)
SELECT CAST(row_number() OVER (ORDER BY c.city_key, s.detid) AS INTEGER) AS detector_key,
       c.city_key,
       CAST(coalesce(l.link_key, 0) AS INTEGER) AS link_key,
       CAST(coalesce(rc.road_class_key, 0) AS SMALLINT) AS road_class_key,
       s.detid, s."long", s.lat, coalesce(s.lanes, 1) AS lanes,
       s.lane_length_km AS monitored_lane_length_km,   -- NULL nếu nguồn thiếu (không điền giá trị giả)
       s.pos_km AS distance_to_downstream_signal_km,
       s.road, s.speed_limit_kmh,
       (l.link_key IS NOT NULL) AS is_link_matched,
       TRUE AS reports_flow, TRUE AS reports_occupancy, 'flow+occ' AS availability_pattern,
       s.has_location_issue, s.has_geometry_attr_issue, s.is_inferred,
       -- Cột SCD loại 2: UTD19 chỉ có một phiên bản thuộc tính detector, nên mỗi detector có đúng 1 dòng hiện hành.
       -- Khi thuộc tính đổi (dời vị trí, đổi loại đường), đóng dòng cũ (valid_to, is_current = FALSE) và thêm dòng mới.
       DATE '{DIM_DATE_START}' AS valid_from, DATE '9999-12-31' AS valid_to, TRUE AS is_current
FROM src s JOIN dw.dim_city c ON c.citycode = s.citycode
     LEFT JOIN dw.dim_link l ON l.city_key = c.city_key AND l.linkid = s.linkid
     LEFT JOIN dw.dim_road_class rc ON rc.fclass = s.fclass
UNION ALL BY NAME
SELECT 0 AS detector_key, CAST(0 AS SMALLINT) AS city_key, 0 AS link_key, CAST(0 AS SMALLINT) AS road_class_key, 'unknown' AS detid,
       FALSE AS is_link_matched, FALSE AS reports_flow, FALSE AS reports_occupancy, 'none' AS availability_pattern,
       FALSE AS has_location_issue, FALSE AS has_geometry_attr_issue, FALSE AS is_inferred,
       DATE '{DIM_DATE_START}' AS valid_from, DATE '9999-12-31' AS valid_to, TRUE AS is_current;

CREATE OR REPLACE TABLE etl.detector_map AS
SELECT c.citycode AS city, d.detid, d.detector_key FROM dw.dim_detector d JOIN dw.dim_city c USING (city_key) WHERE d.detector_key > 0 AND d.is_current;
