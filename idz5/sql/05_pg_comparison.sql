\pset pager off
\timing on

\o idz5/checks/pg_vs_manticore.txt

SELECT 'PostgreSQL vs ManticoreSearch full-text search comparison' AS section;

SELECT 'ManticoreSearch baseline from checks/basic_search.txt' AS section;

SELECT
    'ManticoreSearch' AS system,
    'MATCH(''wireless bluetooth headphones'')' AS query_type,
    '0.0704 sec' AS elapsed_time,
    'BM25 / WEIGHT()' AS ranking;

DROP TABLE IF EXISTS pg_products;

CREATE TABLE pg_products (
    id            BIGINT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL,
    category      TEXT NOT NULL,
    brand         TEXT NOT NULL,
    price         NUMERIC NOT NULL,
    rating        NUMERIC NOT NULL,
    reviews_count INTEGER NOT NULL,
    in_stock      BOOLEAN NOT NULL,
    tags          JSONB NOT NULL,
    created_at    TIMESTAMP NOT NULL
);

INSERT INTO pg_products (
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
SELECT
    product_id AS id,

    brand || ' ' ||
    CASE product_id % 10
        WHEN 0 THEN 'Wireless Bluetooth Headphones'
        WHEN 1 THEN 'Noise Cancelling Headphones'
        WHEN 2 THEN 'Portable Speaker'
        WHEN 3 THEN 'Laptop Pro'
        WHEN 4 THEN 'Smart Phone'
        WHEN 5 THEN 'Gaming Mouse'
        WHEN 6 THEN 'Gaming Keyboard'
        WHEN 7 THEN 'USB Hub'
        WHEN 8 THEN 'Smart Home Camera'
        ELSE 'Gaming Laptop'
    END || ' ' || product_id AS title,

    CASE product_id % 10
        WHEN 0 THEN 'Wireless bluetooth headphones with noise cancelling, soft ear pads and long battery life.'
        WHEN 1 THEN 'Premium noise cancelling headphones for travel, music and online calls.'
        WHEN 2 THEN 'Compact portable wireless speaker with bluetooth connection and strong bass.'
        WHEN 3 THEN 'Powerful laptop for work, study and gaming with fast SSD and bright display.'
        WHEN 4 THEN 'Modern phone with black color option, large screen and fast charging.'
        WHEN 5 THEN 'Gaming mouse with RGB lighting, high precision sensor and programmable buttons.'
        WHEN 6 THEN 'Mechanical gaming keyboard with fast switches and customizable lighting.'
        WHEN 7 THEN 'Compact USB hub for laptop, phone and desktop accessories.'
        WHEN 8 THEN 'Smart camera for home security with mobile app and night mode.'
        ELSE 'Gaming laptop with powerful graphics card, cooling system and fast processor.'
    END || ' Brand: ' || brand || '. Color: ' || color_name AS description,

    CASE product_id % 10
        WHEN 0 THEN 'Audio'
        WHEN 1 THEN 'Audio'
        WHEN 2 THEN 'Audio'
        WHEN 3 THEN 'Computers'
        WHEN 4 THEN 'Mobile'
        WHEN 5 THEN 'Gaming'
        WHEN 6 THEN 'Gaming'
        WHEN 7 THEN 'Accessories'
        WHEN 8 THEN 'Home Electronics'
        ELSE 'Computers'
    END AS category,

    brand,

    CASE product_id % 10
        WHEN 0 THEN 7990
        WHEN 1 THEN 12990
        WHEN 2 THEN 4990
        WHEN 3 THEN 54990
        WHEN 4 THEN 39990
        WHEN 5 THEN 2990
        WHEN 6 THEN 6990
        WHEN 7 THEN 1990
        WHEN 8 THEN 5990
        ELSE 74990
    END + (product_id % 2500) AS price,

    LEAST(5.0, 3.5 + ((product_id % 16)::NUMERIC / 10)) AS rating,

    10 + (product_id % 5000) AS reviews_count,

    product_id % 7 <> 0 AS in_stock,

    jsonb_build_object(
        'color', color_name,
        'warranty', '12 months',
        'delivery', CASE WHEN product_id % 3 = 0 THEN 'express' ELSE 'standard' END,
        'origin', 'generated'
    ) AS tags,

    now() - ((product_id % 10000) || ' seconds')::interval AS created_at

FROM (
    SELECT
        gs AS product_id,
        CASE gs % 10
            WHEN 0 THEN 'Sony'
            WHEN 1 THEN 'Samsung'
            WHEN 2 THEN 'Apple'
            WHEN 3 THEN 'Lenovo'
            WHEN 4 THEN 'Asus'
            WHEN 5 THEN 'Logitech'
            WHEN 6 THEN 'Xiaomi'
            WHEN 7 THEN 'JBL'
            WHEN 8 THEN 'HyperX'
            ELSE 'Dell'
        END AS brand,
        CASE
            WHEN gs % 10 = 4 THEN 'black'
            WHEN gs % 5 = 0 THEN 'black'
            WHEN gs % 5 = 1 THEN 'white'
            WHEN gs % 5 = 2 THEN 'silver'
            WHEN gs % 5 = 3 THEN 'blue'
            ELSE 'red'
        END AS color_name
    FROM generate_series(1, 100000) AS gs
) source_data;

ALTER TABLE pg_products
ADD COLUMN tsv tsvector
GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, ''))
) STORED;

CREATE INDEX idx_pg_products_tsv ON pg_products USING GIN(tsv);

ANALYZE pg_products;

SELECT 'PostgreSQL table loaded' AS section;

SELECT COUNT(*) AS pg_products_count
FROM pg_products;

SELECT 'PostgreSQL full-text search results' AS section;

SELECT
    title,
    ts_rank(tsv, q) AS rank
FROM pg_products,
     to_tsquery('english', 'wireless & bluetooth & headphones') q
WHERE tsv @@ q
ORDER BY rank DESC
LIMIT 10;

SELECT 'PostgreSQL EXPLAIN ANALYZE' AS section;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    title,
    ts_rank(tsv, q) AS rank
FROM pg_products,
     to_tsquery('english', 'wireless & bluetooth & headphones') q
WHERE tsv @@ q
ORDER BY rank DESC
LIMIT 10;

SELECT 'Comparison table draft' AS section;

SELECT
    'Search engine / DB' AS characteristic,
    'ManticoreSearch' AS manticore,
    'PostgreSQL tsvector + GIN' AS postgresql
UNION ALL
SELECT
    'Documents',
    '100000',
    '100000'
UNION ALL
SELECT
    'Search query',
    'MATCH(''wireless bluetooth headphones'')',
    'to_tsquery(''english'', ''wireless & bluetooth & headphones'')'
UNION ALL
SELECT
    'Ranking',
    'BM25 / WEIGHT()',
    'ts_rank'
UNION ALL
SELECT
    'Manticore measured time',
    '0.0704 sec',
    'see PostgreSQL EXPLAIN ANALYZE above'
UNION ALL
SELECT
    'Morphology',
    'stem_enru in index settings',
    'english text search configuration'
UNION ALL
SELECT
    'Facets',
    'native FACET syntax',
    'manual GROUP BY queries'
UNION ALL
SELECT
    'JSON attributes',
    'json field and filters like tags.color',
    'jsonb field and PostgreSQL JSON operators'
UNION ALL
SELECT
    'Transactions',
    'no classic SQL transactions',
    'yes'
UNION ALL
SELECT
    'Best use case',
    'full-text search in product catalog',
    'transactional data with built-in search';

\o