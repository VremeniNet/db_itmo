SET client_encoding = 'UTF8';
SET synchronous_commit = off;

INSERT INTO categories (name)
VALUES
    ('Electronics'),
    ('Computers'),
    ('Mobile'),
    ('Audio'),
    ('Gaming'),
    ('Accessories'),
    ('Home'),
    ('Kitchen'),
    ('Books'),
    ('Sports'),
    ('Clothing'),
    ('Shoes'),
    ('Beauty'),
    ('Health'),
    ('Automotive'),
    ('Garden'),
    ('Toys'),
    ('Office'),
    ('Photography'),
    ('Pet Supplies');

INSERT INTO customers (
    full_name,
    email,
    region,
    created_at
)
SELECT
    concat('Customer ', g),
    concat('customer', g, '@example.com'),
    (
        ARRAY[
            'North',
            'South',
            'East',
            'West',
            'Central'
        ]
    )[1 + ((g - 1) % 5)::INTEGER],
    now() - ((g % 1000) * interval '1 hour')
FROM generate_series(1, 100000) AS g;

INSERT INTO products (
    category_id,
    name,
    price,
    created_at
)
SELECT
    1 + ((g - 1) % 20)::INTEGER,
    concat(
        'Product ',
        lpad(g::TEXT, 5, '0')
    ),
    round(
        (
            10
            + (g % 5000) * 0.25
        )::NUMERIC,
        2
    ),
    now() - ((g % 365) * interval '1 day')
FROM generate_series(1, 10000) AS g;

INSERT INTO orders (
    customer_id,
    order_date,
    status
)
SELECT
    1 + ((g - 1) % 100000),
    now()
        - ((g % 365) * interval '1 day')
        - ((g % 86400) * interval '1 second'),
    (
        ARRAY[
            'new',
            'paid',
            'shipped',
            'completed',
            'cancelled'
        ]
    )[1 + ((g - 1) % 5)::INTEGER]
FROM generate_series(1, 500000) AS g;

WITH generated_items AS (
    SELECT
        o.order_id,
        line_no,
        (
            1
            + (
                (
                    o.order_id * 31
                    + line_no * 17
                ) % 10000
            )
        )::BIGINT AS product_id
    FROM orders AS o
    CROSS JOIN generate_series(1, 2) AS line_no
)
INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
SELECT
    order_id,
    product_id,
    1 + ((order_id + line_no) % 5)::INTEGER,
    round(
        (
            10
            + (product_id % 5000) * 0.25
        )::NUMERIC,
        2
    )
FROM generated_items;

WITH generated_reviews AS (
    SELECT
        g,
        1 + ((g - 1) % 10000) AS product_id,
        1 + ((g * 17 - 1) % 100000) AS customer_id,
        1 + (((g - 1) / 10000) % 5)::INTEGER
            AS rating
    FROM generate_series(1, 200000) AS g
)
INSERT INTO reviews (
    product_id,
    customer_id,
    rating,
    title,
    body,
    created_at
)
SELECT
    product_id,
    customer_id,
    rating,
    CASE
        WHEN rating >= 4 THEN
            'Отличный товар'
        WHEN rating = 3 THEN
            'Обычный товар'
        ELSE
            'Проблема с товаром'
    END,
    CASE
        WHEN rating >= 4 THEN
            concat(
                'Отличный товар, рекомендую. ',
                'Хорошее качество сборки, ',
                'удобное использование и быстрая доставка. ',
                'Номер отзыва: ',
                g,
                '.'
            )
        WHEN rating = 3 THEN
            concat(
                'Обычный товар. ',
                'Качество сборки среднее, ',
                'характеристики соответствуют описанию. ',
                'Номер отзыва: ',
                g,
                '.'
            )
        ELSE
            concat(
                'Обнаружен брак, товар сломался. ',
                'Потребовался возврат и обращение в поддержку. ',
                'Номер отзыва: ',
                g,
                '.'
            )
    END,
    now()
        - ((g % 365) * interval '1 day')
        - ((g % 86400) * interval '1 second')
FROM generated_reviews;

ANALYZE categories;
ANALYZE customers;
ANALYZE products;
ANALYZE orders;
ANALYZE order_items;
ANALYZE reviews;