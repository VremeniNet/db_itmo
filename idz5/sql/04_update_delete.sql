
SELECT id, title, price, rating
FROM products
WHERE id = 4;

UPDATE products
SET price = 29999, rating = 4.9
WHERE id = 4;

SELECT id, title, price, rating
FROM products
WHERE id = 4;



REPLACE INTO products (
    id,
    title,
    description,
    category,
    brand,
    price,
    rating,
    reviews_count,
    in_stock,
    tags,
    created_at
)
VALUES (
    200001,
    'Delete Demo Unique Headphones',
    'Temporary product for delete demonstration with unique delete marker.',
    'Audio',
    'DemoBrand',
    9999,
    4.5,
    10,
    1,
    '{"color":"black","origin":"delete_demo"}',
    1735689600
);

SELECT id, title
FROM products
WHERE MATCH('delete demo unique')
LIMIT 10;

DELETE FROM products
WHERE id = 200001;

SELECT id, title
FROM products
WHERE MATCH('delete demo unique')
LIMIT 10;



REPLACE INTO products (
    id,
    title,
    description,
    category,
    brand,
    price,
    rating,
    reviews_count,
    in_stock,
    tags,
    created_at
)
VALUES (
    200002,
    'Replace Demo Old Product',
    'Old version of product before replace operation.',
    'Accessories',
    'DemoBrand',
    1000,
    3.0,
    1,
    1,
    '{"color":"white","version":"old"}',
    1735689600
);

SELECT id, title, price, rating, tags
FROM products
WHERE id = 200002;

REPLACE INTO products (
    id,
    title,
    description,
    category,
    brand,
    price,
    rating,
    reviews_count,
    in_stock,
    tags,
    created_at
)
VALUES (
    200002,
    'Replace Demo New Product',
    'New version of product after replace operation.',
    'Accessories',
    'DemoBrand',
    2500,
    4.8,
    25,
    1,
    '{"color":"blue","version":"new"}',
    1735689600
);

SELECT id, title, price, rating, tags
FROM products
WHERE id = 200002;

SELECT id, title
FROM products
WHERE MATCH('replace demo old')
LIMIT 10;

SELECT id, title
FROM products
WHERE MATCH('replace demo new')
LIMIT 10;