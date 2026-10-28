CREATE OR REPLACE TABLE dw.dim_link AS
SELECT CAST(row_number() OVER (ORDER BY l.linkid) AS INTEGER) AS link_key, 
       c.city_key, 
       l.linkid, 
       CAST(l.n_waypoints AS INTEGER) AS n_waypoints,
       l.geometry_wkt, l.geometry_length_km, l.start_long, l.start_lat, l.end_long, l.end_lat,
       l.has_geometry_issue
FROM clean.links l JOIN dw.dim_city c ON c.citycode = l.citycode
UNION ALL BY NAME
SELECT 0 AS link_key, CAST(0 AS SMALLINT) AS city_key, 'unknown' AS linkid, 0 AS n_waypoints, FALSE AS has_geometry_issue;