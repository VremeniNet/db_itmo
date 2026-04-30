SET client_encoding = 'UTF8';

DROP TABLE IF EXISTS order_items_1nf;
DROP TABLE IF EXISTS orders_1nf;

CREATE TABLE orders_1nf (
    order_id INTEGER PRIMARY KEY,
    order_date DATE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    total_amount NUMERIC NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE order_items_1nf (
    order_id INTEGER NOT NULL,
    item_position INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    product_price NUMERIC NOT NULL,
    product_quantity INTEGER NOT NULL,

    PRIMARY KEY (order_id, item_position),
    FOREIGN KEY (order_id) REFERENCES orders_1nf(order_id) ON DELETE CASCADE
);

INSERT INTO orders_1nf (
    order_id,
    order_date,
    customer_name,
    customer_email,
    customer_phone,
    delivery_address,
    total_amount,
    status
)
SELECT
    order_id,
    order_date,
    customer_name,
    customer_email,
    customer_phone,
    delivery_address,
    total_amount,
    status
FROM orders_raw;

WITH raw_items AS (
    SELECT
        order_id,
        regexp_split_to_array(product_names, '\s*,\s*') AS names,
        regexp_split_to_array(product_prices, '\s*,\s*') AS prices,
        regexp_split_to_array(product_quantities, '\s*,\s*') AS quantities
    FROM orders_raw
)
INSERT INTO order_items_1nf (
    order_id,
    item_position,
    product_name,
    product_price,
    product_quantity
)
SELECT
    order_id,
    item_index,
    names[item_index] AS product_name,
    prices[item_index]::NUMERIC AS product_price,
    quantities[item_index]::INTEGER AS product_quantity
FROM raw_items
CROSS JOIN LATERAL generate_subscripts(names, 1) AS item_index;

SELECT COUNT(*) AS orders_1nf_count
FROM orders_1nf;

SELECT COUNT(*) AS order_items_1nf_count
FROM order_items_1nf;

SELECT *
FROM order_items_1nf
ORDER BY order_id, item_position
LIMIT 10;