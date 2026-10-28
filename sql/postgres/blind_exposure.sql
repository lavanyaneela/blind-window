-- columns: day, served_cumulative, labeled_cumulative, labeled_share
-- The exposure curve: predictions served since onset against labels arrived,
-- day by day. The gap between the two lines is the blind window made visible.
WITH days AS (
    SELECT d.day::integer AS day
    FROM generate_series(CEIL(%(onset)s)::bigint, CEIL(%(asof)s)::bigint) AS d(day)
),
per_day AS (
    SELECT
        days.day,
        (SELECT COUNT(*) FROM predictions p
         WHERE p.ts_day >= %(onset)s
           AND p.ts_day < LEAST(days.day::double precision, %(asof)s)) AS served_cumulative,
        (SELECT COUNT(*) FROM predictions p JOIN labels l USING (request_id)
         WHERE p.ts_day >= %(onset)s
           AND l.label_day <= LEAST(days.day::double precision, %(asof)s)) AS labeled_cumulative
    FROM days
)
SELECT
    day,
    served_cumulative,
    labeled_cumulative,
    CASE WHEN served_cumulative = 0 THEN 0.0
         ELSE labeled_cumulative::double precision / served_cumulative END AS labeled_share
FROM per_day
ORDER BY day
