
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('wireless bluetooth headphones')
ORDER BY w DESC
LIMIT 10;



SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('"noise cancelling"')
ORDER BY w DESC
LIMIT 10;



SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('"portable speaker"~3')
ORDER BY w DESC
LIMIT 10;



SELECT id, title, price, rating
FROM products
WHERE MATCH('laptop')
  AND price BETWEEN 30000 AND 80000
  AND rating >= 4.0
ORDER BY rating DESC
LIMIT 10;



SELECT id, title, tags
FROM products
WHERE MATCH('phone')
  AND tags.color = 'black'
LIMIT 10;