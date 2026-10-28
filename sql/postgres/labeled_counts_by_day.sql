-- columns: day, n_labeled_post_onset
-- Cumulative count of post-onset predictions whose label has arrived by each
-- whole day up to asof. The denominator of every "what is confirmable" claim.
SELECT
    d.day::integer AS day,
    (
        SELECT COUNT(*)
        FROM predictions p
        JOIN labels l USING (request_id)
        WHERE p.ts_day >= %(onset)s AND l.label_day <= LEAST(d.day::double precision, %(asof)s)
    ) AS n_labeled_post_onset
FROM generate_series(CEIL(%(onset)s)::bigint, CEIL(%(asof)s)::bigint) AS d(day)
ORDER BY day
