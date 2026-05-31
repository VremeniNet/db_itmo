SET client_encoding = 'UTF8';
SET client_min_messages = WARNING;

\pset pager off
\pset footer off

DROP MATERIALIZED VIEW IF EXISTS mv_monthly_sales;

\echo '1. Query from normalized tables'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    date_trunc('month', o.order_date) AS month,
    p.name AS product_name,
    c.name AS category_name,
    SUM(oi.quantity) AS total_qty,
    SUM(oi.quantity * oi.price_at_order) AS total_revenue
FROM order_items oi
JOIN orders o
    ON o.order_id = oi.order_id
JOIN products p
    ON p.product_id = oi.product_id
JOIN categories c
    ON c.category_id = p.category_id
GROUP BY
    date_trunc('month', o.order_date),
    p.name,
    c.name
ORDER BY
    month,
    product_name;

\echo '2. Create materialized view'

CREATE MATERIALIZED VIEW mv_monthly_sales AS
SELECT
    date_trunc('month', o.order_date) AS month,
    p.name AS product_name,
    c.name AS category_name,
    SUM(oi.quantity) AS total_qty,
    SUM(oi.quantity * oi.price_at_order) AS total_revenue
FROM order_items oi
JOIN orders o
    ON o.order_id = oi.order_id
JOIN products p
    ON p.product_id = oi.product_id
JOIN categories c
    ON c.category_id = p.category_id
GROUP BY
    date_trunc('month', o.order_date),
    p.name,
    c.name;

\echo '3. Query from materialized view'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    month,
    product_name,
    category_name,
    total_qty,
    total_revenue
FROM mv_monthly_sales
ORDER BY
    month,
    product_name;

\echo '4. Example data from materialized view'

SELECT
    month,
    product_name,
    category_name,
    total_qty,
    total_revenue
FROM mv_monthly_sales
ORDER BY
    month,
    product_name
LIMIT 10;