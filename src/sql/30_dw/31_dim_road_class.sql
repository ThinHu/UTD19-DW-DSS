-- dim_road_class: phân cấp Nhóm đường → Loại đường (OSM fclass). Trước đây road_group gán cứng 'Arterial'.
CREATE OR REPLACE TABLE dw.dim_road_class AS
WITH src AS (SELECT DISTINCT fclass FROM clean.detectors WHERE fclass IS NOT NULL)
SELECT CAST(row_number() OVER (ORDER BY fclass) AS SMALLINT) AS road_class_key,
       fclass,
       CASE regexp_replace(fclass, '_link$', '')
            WHEN 'motorway' THEN 'Cao tốc' WHEN 'trunk' THEN 'Quốc lộ' WHEN 'primary' THEN 'Đường chính'
            WHEN 'secondary' THEN 'Đường cấp 2' WHEN 'tertiary' THEN 'Đường cấp 3'
            WHEN 'residential' THEN 'Đường khu dân cư' ELSE 'Khác' END
         || CASE WHEN fclass LIKE '%\_link' ESCAPE '\' THEN ' (nhánh nối)' ELSE '' END AS fclass_description,
       CASE WHEN regexp_replace(fclass, '_link$', '') IN ('motorway', 'trunk') THEN 'Cao tốc / quốc lộ'
            WHEN regexp_replace(fclass, '_link$', '') IN ('primary', 'secondary') THEN 'Trục chính'
            WHEN regexp_replace(fclass, '_link$', '') = 'tertiary' THEN 'Đường gom'
            ELSE 'Nội bộ / khác' END AS road_group,
       CAST(CASE WHEN regexp_replace(fclass, '_link$', '') IN ('motorway', 'trunk') THEN 1
                 WHEN regexp_replace(fclass, '_link$', '') = 'primary' THEN 2
                 WHEN regexp_replace(fclass, '_link$', '') = 'secondary' THEN 3
                 WHEN regexp_replace(fclass, '_link$', '') = 'tertiary' THEN 4 ELSE 5 END AS TINYINT) AS hierarchy_rank
FROM src
UNION ALL BY NAME
SELECT CAST(0 AS SMALLINT) AS road_class_key, 'unknown' AS fclass, 'Không xác định' AS fclass_description,
       'Không xác định' AS road_group, CAST(9 AS TINYINT) AS hierarchy_rank;
