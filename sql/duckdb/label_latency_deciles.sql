-- columns: decile, n, min_delay_days, median_delay_days, max_delay_days
-- NTILE deciles of observed label latency among labels arrived by $asof.
-- Observed latency is right-censored: slow labels are still missing, so these
-- deciles understate the true delay. The caveat is ADR-005.
WITH observed AS (
    SELECT l.label_day - p.ts_day AS delay_days
    FROM predictions p
    JOIN labels l USING (request_id)
    WHERE l.label_day <= $asof
),
ranked AS (
    SELECT delay_days, NTILE(10) OVER (ORDER BY delay_days) AS decile
    FROM observed
)
SELECT
    decile,
    COUNT(*) AS n,
    MIN(delay_days) AS min_delay_days,
    quantile_cont(delay_days, 0.5) AS median_delay_days,
    MAX(delay_days) AS max_delay_days
FROM ranked
GROUP BY decile
ORDER BY decile
