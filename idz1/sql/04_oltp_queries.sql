SET client_encoding = 'UTF8';

\pset pager off
\pset footer off

\echo '1. Create order: SELECT FOR UPDATE + INSERT INTO orders + INSERT INTO order_items'

BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    name,
    price
FROM products
WHERE product_id = 8
FOR UPDATE;

EXPLAIN (ANALYZE, BUFFERS)
INSERT INTO orders (
    order_id,
    customer_id,
    address_id,
    order_date,
    status,
    total_amount
)
VALUES (
    999999,
    1,
    1,
    CURRENT_DATE,
    'new',
    3000
);

EXPLAIN (ANALYZE, BUFFERS)
INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    price_at_order
)
SELECT
    999999,
    product_id,
    2,
    price
FROM products
WHERE product_id = 8;

ROLLBACK;

\echo '2. Update order status'

BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE orders
SET status = 'shipped'
WHERE order_id = 1;

ROLLBACK;

\echo '3. Get order with JOIN by 4 tables'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.order_date,
    o.status,
    o.total_amount,
    c.name AS customer_name,
    c.email AS customer_email,
    p.name AS product_name,
    oi.quantity,
    oi.price_at_order
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
JOIN order_items oi
    ON oi.order_id = o.order_id
JOIN products p
    ON p.product_id = oi.product_id
WHERE o.order_id = 1;

\echo '4. Report: top-10 products by sold quantity'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.product_id,
    p.name AS product_name,
    SUM(oi.quantity) AS total_sold,
    SUM(oi.quantity * oi.price_at_order) AS total_revenue
FROM order_items oi
JOIN products p
    ON p.product_id = oi.product_id
GROUP BY
    p.product_id,
    p.name
ORDER BY total_sold DESC
LIMIT 10;

\echo '5. Search customer by email'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    name,
    email,
    phone
FROM customers
WHERE email = 'ivanov@example.com';

\echo '6. Search customer by name substring with ILIKE'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    name,
    email,
    phone
FROM customers
WHERE name ILIKE U&'%\0418\0432\0430\043D%';