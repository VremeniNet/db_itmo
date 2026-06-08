\pset pager off
\timing on

SELECT
    'categories' AS table_name,
    count(*) AS rows
FROM categories

UNION ALL

SELECT
    'customers',
    count(*)
FROM customers

UNION ALL

SELECT
    'products',
    count(*)
FROM products

UNION ALL

SELECT
    'orders',
    count(*)
FROM orders

UNION ALL

SELECT
    'order_items',
    count(*)
FROM order_items

UNION ALL

SELECT
    'reviews',
    count(*)
FROM reviews

ORDER BY table_name;


-- Создание заказа в транзакции

BEGIN;

INSERT INTO orders (
    customer_id,
    order_date,
    status
)
VALUES (
    42,
    now(),
    'new'
)
RETURNING order_id
\gset

INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES
    (
        :order_id,
        42,
        2,
        (
            SELECT price
            FROM products
            WHERE product_id = 42
        )
    ),
    (
        :order_id,
        142,
        1,
        (
            SELECT price
            FROM products
            WHERE product_id = 142
        )
    );

COMMIT;

\echo Created order ID: :order_id


-- Чтение заказа с JOIN

SELECT
    o.order_id,
    o.order_date,
    o.status,
    c.customer_id,
    c.full_name AS customer_name,
    c.email,
    c.region,
    count(oi.order_item_id) AS positions_count,
    sum(oi.quantity) AS items_count,
    round(
        sum(oi.quantity * oi.unit_price),
        2
    ) AS order_total
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.order_id = :order_id
GROUP BY
    o.order_id,
    o.order_date,
    o.status,
    c.customer_id,
    c.full_name,
    c.email,
    c.region;


-- Детализация заказа

SELECT
    o.order_id,
    p.product_id,
    p.name AS product_name,
    c.name AS category,
    oi.quantity,
    oi.unit_price,
    round(
        oi.quantity * oi.unit_price,
        2
    ) AS line_total
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN products AS p
    ON p.product_id = oi.product_id
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE o.order_id = :order_id
ORDER BY oi.order_item_id;


-- Обновление статуса

UPDATE orders
SET status = 'paid'
WHERE order_id = :order_id;

SELECT
    order_id,
    status,
    order_date
FROM orders
WHERE order_id = :order_id;