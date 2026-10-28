-- columns: day, served_cumulative, labeled_cumulative, labeled_share
-- The exposure curve: predictions served since onset against labels arrived,
-- day by day. The gap between the two lines is the blind window made visible.
WITH days AS (
    SELECT CAST(d.range AS INTEGER) AS day
    FROM range(CAST(CEIL($onset) AS BIGINT), CAST(CEIL($asof) AS BIGINT) + 1) AS d
),
per_day AS (
    SELECT
        days.day,
        (SELECT COUNT(*) FROM predictions p
         WHERE p.ts_day >= $onset
           AND p.ts_day < LEAST(CAST(days.day AS DOUBLE), $asof)) AS served_cumulative,
        (SELECT COUNT(*) FROM predictions p JOIN labels l USING (request_id)
         WHERE p.ts_day >= $onset
           AND l.label_day <= LEAST(CAST(days.day AS DOUBLE), $asof)) AS labeled_cumulative
    FROM days
)
SELECT
    day,
    served_cumulative,
    labeled_cumulative,
    CASE WHEN served_cumulative = 0 THEN 0.0
         ELSE CAST(labeled_cumulative AS DOUBLE) / served_cumulative END AS labeled_share
FROM per_day
ORDER BY day
