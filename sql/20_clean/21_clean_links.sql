CREATE OR REPLACE TABLE clean.link_waypoints AS
SELECT lower(trim(coalesce(citycode, 'luzern'))) AS citycode, 
       NULLIF(regexp_replace(trim(linkid), '\.0$', ''), '') AS linkid,
       TRY_CAST("order" AS INTEGER) AS wp_order, 
       TRY_CAST(piece AS INTEGER) AS piece, 
       NULLIF(trim("group"), '') AS group_id,
       TRY_CAST("long" AS DOUBLE) AS "long", 
       TRY_CAST(lat AS DOUBLE) AS lat
FROM stg.links_raw
WHERE linkid IS NOT NULL AND lat IS NOT NULL AND "long" IS NOT NULL;

CREATE OR REPLACE TABLE clean.links AS
SELECT citycode, linkid, count(*) AS n_waypoints,
       'LINESTRING(' || string_agg(CAST("long" AS VARCHAR) || ' ' || CAST(lat AS VARCHAR), ', ' ORDER BY wp_order) || ')' AS geometry_wkt,
       0.5 AS geometry_length_km,
       arg_min("long", wp_order) AS start_long, arg_min(lat, wp_order) AS start_lat,
       arg_max("long", wp_order) AS end_long, arg_max(lat, wp_order) AS end_lat,
       FALSE AS has_geometry_issue
FROM clean.link_waypoints GROUP BY citycode, linkid;