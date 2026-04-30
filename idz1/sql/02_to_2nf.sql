SET client_encoding = 'UTF8';

DROP TABLE IF EXISTS order_items_2nf;
DROP TABLE IF EXISTS orders_2nf;
DROP TABLE IF EXISTS products_2nf;
DROP TABLE IF EXISTS customers_2nf;

CREATE TABLE customers_2nf (
    customer_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL
);

CREATE TABLE products_2nf (
    product_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    price NUMERIC NOT NULL CHECK (price >= 0)
);

CREATE TABLE orders_2nf (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    delivery_address TEXT NOT NULL,
    total_amount NUMERIC NOT NULL CHECK (total_amount >= 0),
    status TEXT NOT NULL,

    FOREIGN KEY (customer_id) REFERENCES customers_2nf(customer_id)
);

CREATE TABLE order_items_2nf (
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price_at_order NUMERIC NOT NULL CHECK (price_at_order >= 0),

    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES orders_2nf(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products_2nf(product_id)
);

INSERT INTO customers_2nf (
    name,
    email,
    phone
)
SELECT DISTINCT
    customer_name,
    customer_email,
    customer_phone
FROM orders_1nf
ORDER BY customer_email;

INSERT INTO products_2nf (
    name,
    price
)
SELECT DISTINCT
    product_name,
    product_price
FROM order_items_1nf
ORDER BY product_name;

INSERT INTO orders_2nf (
    order_id,
    customer_id,
    order_date,
    delivery_address,
    total_amount,
    status
)
SELECT
    o.order_id,
    c.customer_id,
    o.order_date,
    o.delivery_address,
    o.total_amount,
    o.status
FROM orders_1nf o
JOIN customers_2nf c
    ON c.email = o.customer_email
ORDER BY o.order_id;

INSERT INTO order_items_2nf (
    order_id,
    product_id,
    quantity,
    price_at_order
)
SELECT
    oi.order_id,
    p.product_id,
    oi.product_quantity,
    oi.product_price
FROM order_items_1nf oi
JOIN products_2nf p
    ON p.name = oi.product_name
ORDER BY oi.order_id, p.product_id;

SELECT 'customers_2nf' AS table_name, COUNT(*) AS rows_count
FROM customers_2nf
UNION ALL
SELECT 'products_2nf' AS table_name, COUNT(*) AS rows_count
FROM products_2nf
UNION ALL
SELECT 'orders_2nf' AS table_name, COUNT(*) AS rows_count
FROM orders_2nf
UNION ALL
SELECT 'order_items_2nf' AS table_name, COUNT(*) AS rows_count
FROM order_items_2nf;