-- columns: model_version, served_from_day, served_to_day, n_predictions, n_labeled_asof, labeled_share
-- Serving window and label coverage per registered model version as of $asof.
-- This is what names the version at risk when the tool refuses.
SELECT
    p.model_version,
    MIN(p.ts_day) AS served_from_day,
    MAX(p.ts_day) AS served_to_day,
    COUNT(*) AS n_predictions,
    COUNT(l.request_id) AS n_labeled_asof,
    CAST(COUNT(l.request_id) AS DOUBLE) / COUNT(*) AS labeled_share
FROM predictions p
LEFT JOIN labels l
    ON p.request_id = l.request_id AND l.label_day <= $asof
GROUP BY p.model_version
ORDER BY served_from_day
