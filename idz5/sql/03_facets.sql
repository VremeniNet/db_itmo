
SELECT
    category,
    COUNT(*) AS cnt,
    AVG(price) AS avg_price
FROM products
WHERE MATCH('gaming')
GROUP BY category
ORDER BY cnt DESC;



SELECT id, title, price
FROM products
WHERE MATCH('gaming')
LIMIT 10
FACET category ORDER BY COUNT(*) DESC
FACET brand ORDER BY COUNT(*) DESC;