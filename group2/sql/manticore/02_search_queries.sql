-- Полнотекстовый поиск положительных отзывов

SELECT
    id,
    title,
    rating,
    WEIGHT() AS weight
FROM reviews
WHERE MATCH('отличный товар рекомендую')
ORDER BY weight DESC
LIMIT 10;


-- Фильтрация по рейтингу и товару

SELECT
    id,
    title,
    product_id,
    rating
FROM reviews
WHERE rating >= 4
  AND product_id = 42
ORDER BY
    rating DESC,
    id
LIMIT 20;


-- Фасетный поиск по рейтингу

SELECT
    id,
    title,
    rating
FROM reviews
WHERE MATCH('товар')
LIMIT 10
FACET rating
ORDER BY COUNT(*) DESC;


-- Поиск негативных отзывов

SELECT
    id,
    title,
    rating,
    WEIGHT() AS weight
FROM reviews
WHERE MATCH('брак сломался возврат')
ORDER BY weight DESC
LIMIT 10;