SET client_encoding = 'UTF8';
SET client_min_messages = WARNING;

\pset pager off
\pset footer off

ALTER TABLE order_items
DROP COLUMN IF EXISTS product_name;

ALTER TABLE order_items
ADD COLUMN product_name TEXT;

UPDATE order_items oi
SET product_name = p.name
FROM products p
WHERE p.product_id = oi.product_id;

\echo '1. Query from normalized tables with JOIN'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    oi.order_id,
    oi.product_id,
    p.name AS product_name,
    oi.quantity,
    oi.price_at_order
FROM order_items oi
JOIN products p
    ON p.product_id = oi.product_id
WHERE oi.order_id = 1;

\echo '2. Query from denormalized order_items without JOIN'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    product_id,
    product_name,
    quantity,
    price_at_order
FROM order_items
WHERE order_id = 1;

\echo '3. Example data from denormalized order_items'

SELECT
    order_id,
    product_id,
    product_name,
    quantity,
    price_at_order
FROM order_items
ORDER BY order_id, product_id
LIMIT 10;