SET client_encoding = 'UTF8';
SET client_min_messages = WARNING;

\pset pager off
\pset footer off

DROP INDEX IF EXISTS idx_order_items_product_id;
DROP INDEX IF EXISTS idx_customers_name_btree;
DROP INDEX IF EXISTS idx_customers_name_trgm;

\echo '1. BEFORE index: search order_items by product_id'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    product_id,
    quantity,
    price_at_order
FROM order_items
WHERE product_id = 8;

\echo '2. Create index on order_items.product_id'

CREATE INDEX idx_order_items_product_id
ON order_items(product_id);

\echo '3. AFTER index: search order_items by product_id'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    product_id,
    quantity,
    price_at_order
FROM order_items
WHERE product_id = 8;

\echo '4. Search customer by email'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    name,
    email,
    phone
FROM customers
WHERE email = 'ivanov@example.com';

\echo '5. BEFORE B-tree index: search customer by name substring'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    name,
    email,
    phone
FROM customers
WHERE name ILIKE U&'%\0418\0432\0430\043D%';

\echo '6. Create B-tree index on customers.name'

CREATE INDEX idx_customers_name_btree
ON customers(name);

\echo '7. AFTER B-tree index: search customer by name substring'

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    name,
    email,
    phone
FROM customers
WHERE name ILIKE U&'%\0418\0432\0430\043D%';

\echo '8. Create pg_trgm extension and GIN index on customers.name'

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_customers_name_trgm
ON customers
USING GIN (name gin_trgm_ops);

\echo '9. AFTER GIN pg_trgm index: search customer by name substring'

SET enable_seqscan = OFF;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    name,
    email,
    phone
FROM customers
WHERE name ILIKE U&'%\0418\0432\0430\043D%';

SET enable_seqscan = ON;