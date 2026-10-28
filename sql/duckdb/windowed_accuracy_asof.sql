-- columns: prediction_day, n_labeled, accuracy
-- Accuracy per prediction day, counting only labels that had arrived by $asof.
-- This is the curve an operator could actually have seen on that date.
SELECT
    CAST(FLOOR(p.ts_day) AS INTEGER) AS prediction_day,
    COUNT(l.request_id) AS n_labeled,
    AVG(CASE WHEN p.predicted = l.y_true THEN 1.0 ELSE 0.0 END) AS accuracy
FROM predictions p
LEFT JOIN labels l
    ON p.request_id = l.request_id AND l.label_day <= $asof
WHERE p.ts_day <= $asof
GROUP BY prediction_day
ORDER BY prediction_day
