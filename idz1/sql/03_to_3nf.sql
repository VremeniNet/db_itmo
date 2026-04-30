SET client_encoding = 'UTF8';

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS addresses;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL
);

CREATE TABLE addresses (
    address_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    address TEXT NOT NULL,

    UNIQUE (customer_id, address),
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE categories (
    category_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category_id INTEGER NOT NULL,
    price NUMERIC NOT NULL CHECK (price >= 0),

    FOREIGN KEY (category_id) REFERENCES categories(category_id)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    address_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC NOT NULL CHECK (total_amount >= 0),

    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (address_id) REFERENCES addresses(address_id)
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    price_at_order NUMERIC NOT NULL CHECK (price_at_order >= 0),

    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

INSERT INTO customers (
    customer_id,
    name,
    email,
    phone
)
SELECT
    customer_id,
    name,
    email,
    phone
FROM customers_2nf
ORDER BY customer_id;

INSERT INTO addresses (
    customer_id,
    address
)
SELECT DISTINCT
    customer_id,
    delivery_address
FROM orders_2nf
ORDER BY customer_id, delivery_address;

INSERT INTO categories (
    name
)
VALUES
    ('Компьютерная техника'),
    ('Периферия'),
    ('Аксессуары');

INSERT INTO products (
    product_id,
    name,
    category_id,
    price
)
SELECT
    p.product_id,
    p.name,
    c.category_id,
    p.price
FROM products_2nf p
JOIN categories c
    ON c.name = CASE
        WHEN p.name IN ('Ноутбук', 'Монитор', 'Внешний SSD') THEN 'Компьютерная техника'
        WHEN p.name IN ('Мышь', 'Клавиатура', 'Веб-камера', 'Наушники') THEN 'Периферия'
        ELSE 'Аксессуары'
    END
ORDER BY p.product_id;

INSERT INTO orders (
    order_id,
    customer_id,
    address_id,
    order_date,
    status,
    total_amount
)
SELECT
    o.order_id,
    o.customer_id,
    a.address_id,
    o.order_date,
    o.status,
    o.total_amount
FROM orders_2nf o
JOIN addresses a
    ON a.customer_id = o.customer_id
   AND a.address = o.delivery_address
ORDER BY o.order_id;

INSERT INTO order_items (
    order_id,
    product_id,
    quantity,
    price_at_order
)
SELECT
    order_id,
    product_id,
    quantity,
    price_at_order
FROM order_items_2nf
ORDER BY order_id, product_id;

SELECT 'customers' AS table_name, COUNT(*) AS rows_count
FROM customers
UNION ALL
SELECT 'addresses' AS table_name, COUNT(*) AS rows_count
FROM addresses
UNION ALL
SELECT 'categories' AS table_name, COUNT(*) AS rows_count
FROM categories
UNION ALL
SELECT 'products' AS table_name, COUNT(*) AS rows_count
FROM products
UNION ALL
SELECT 'orders' AS table_name, COUNT(*) AS rows_count
FROM orders
UNION ALL
SELECT 'order_items' AS table_name, COUNT(*) AS rows_count
FROM order_items;