CREATE OR REPLACE TABLE clean.link_waypoints AS
SELECT lower(trim(coalesce(citycode, 'luzern'))) AS citycode,
       NULLIF(regexp_replace(trim(linkid), '\.0$', ''), '') AS linkid,
       TRY_CAST("order" AS INTEGER) AS wp_order,
       TRY_CAST(piece AS INTEGER) AS piece,
       NULLIF(trim("group"), '') AS group_id,
       TRY_CAST("long" AS DOUBLE) AS "long",
       TRY_CAST(lat AS DOUBLE) AS lat
FROM stg.links_raw
WHERE linkid IS NOT NULL AND TRY_CAST(lat AS DOUBLE) IS NOT NULL AND TRY_CAST("long" AS DOUBLE) IS NOT NULL;

-- Độ dài link = tổng khoảng cách haversine giữa các điểm liên tiếp (trước đây gán cứng 0,5 km).
CREATE OR REPLACE TABLE clean.links AS
WITH seg AS (
    SELECT *,
           lag("long") OVER w AS plong, lag(lat) OVER w AS plat
    FROM clean.link_waypoints
    WINDOW w AS (PARTITION BY citycode, linkid ORDER BY wp_order)
), seg_len AS (
    SELECT *,
           CASE WHEN plat IS NULL THEN 0 ELSE
             2 * 6371.0 * asin(sqrt(pow(sin(radians(lat - plat) / 2), 2) +
                                    cos(radians(plat)) * cos(radians(lat)) * pow(sin(radians("long" - plong) / 2), 2)))
           END AS seg_km
    FROM seg
)
SELECT citycode, linkid, count(*) AS n_waypoints,
       'LINESTRING(' || string_agg(CAST("long" AS VARCHAR) || ' ' || CAST(lat AS VARCHAR), ', ' ORDER BY wp_order) || ')' AS geometry_wkt,
       round(sum(seg_km), 4) AS geometry_length_km,
       arg_min("long", wp_order) AS start_long, arg_min(lat, wp_order) AS start_lat,
       arg_max("long", wp_order) AS end_long, arg_max(lat, wp_order) AS end_lat,
       (count(*) < 2 OR sum(seg_km) = 0) AS has_geometry_issue
FROM seg_len GROUP BY citycode, linkid;
