CREATE OR REPLACE TABLE dw.dim_road_class AS
SELECT CAST(row_number() OVER (ORDER BY fclass) AS SMALLINT) AS road_class_key, 
       fclass, 
       fclass AS fclass_description, 
       'Arterial' AS road_group 
FROM (SELECT DISTINCT fclass FROM clean.detectors WHERE fclass IS NOT NULL)
UNION ALL BY NAME 
SELECT CAST(0 AS SMALLINT) AS road_class_key, 'unknown' AS fclass, 'Unknown' AS fclass_description, 'Other' AS road_group;