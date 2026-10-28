-- columns: age_days, n_labeled_at_age, cumulative_labeled_share
-- For the cohort predicted in [cohort_start, min(cohort_end, asof)): the share of the
-- cohort labeled within k days of prediction, as a cumulative window sum.
-- Ages are capped at $asof so the curve never counts a label from the future.
WITH cohort AS (
    SELECT p.request_id, p.ts_day, l.label_day
    FROM predictions p
    LEFT JOIN labels l
        ON p.request_id = l.request_id AND l.label_day <= $asof
    WHERE p.ts_day >= $cohort_start
      AND p.ts_day < LEAST(CAST($cohort_end AS DOUBLE), $asof)
),
aged AS (
    SELECT CAST(FLOOR(label_day - ts_day) AS INTEGER) AS age_days
    FROM cohort
    WHERE label_day IS NOT NULL
)
SELECT
    age_days,
    COUNT(*) AS n_labeled_at_age,
    SUM(COUNT(*)) OVER (ORDER BY age_days ROWS UNBOUNDED PRECEDING)
        / (SELECT CAST(COUNT(*) AS DOUBLE) FROM cohort) AS cumulative_labeled_share
FROM aged
GROUP BY age_days
ORDER BY age_days
