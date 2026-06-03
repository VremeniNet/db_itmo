CREATE DATABASE IF NOT EXISTS idz2;

DROP TABLE IF EXISTS idz2.orders_ttl;

CREATE TABLE idz2.orders_ttl (
    order_date       Date,
    order_datetime   DateTime,
    order_id         UInt64,
    customer_id      UInt64,
    customer_name    String,
    customer_email   LowCardinality(String),
    region           LowCardinality(String),
    product_id       UInt64,
    product_name     String,
    category         LowCardinality(String),
    quantity         UInt32,
    price            Decimal(12, 2),
    line_total       Decimal(12, 2),
    order_status     LowCardinality(String)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(order_date)
ORDER BY (category, toStartOfHour(order_datetime), order_status);

INSERT INTO idz2.orders_ttl VALUES
(today() - 120, now() - INTERVAL 120 DAY, 900001, 1, 'Ivan Ivanov', 'ivanov@example.com', 'Moscow', 10, 'Laptop', 'Computers', 1, 85000.00, 85000.00, 'delivered'),
(today() - 120, now() - INTERVAL 120 DAY, 900002, 2, 'Petr Petrov', 'petrov@example.com', 'Kazan', 7, 'Monitor', 'Computers', 1, 22000.00, 22000.00, 'delivered'),
(today() - 100, now() - INTERVAL 100 DAY, 900003, 3, 'Anna Sidorova', 'sidorova@example.com', 'Samara', 8, 'Mouse', 'Periphery', 2, 1500.00, 3000.00, 'delivered'),
(today(), now(), 900004, 4, 'Olga Fedorova', 'fedorova@example.com', 'Saint Petersburg', 1, 'USB hub', 'Accessories', 1, 2500.00, 2500.00, 'new'),
(today(), now(), 900005, 5, 'Artem Novikov', 'novikov@example.com', 'Yekaterinburg', 5, 'Keyboard', 'Periphery', 1, 3500.00, 3500.00, 'new');

SELECT 'before_ttl' AS stage, count() AS rows_count
FROM idz2.orders_ttl
FORMAT TabSeparatedWithNames;

SELECT
    'before_ttl' AS stage,
    partition,
    name,
    active,
    rows,
    formatReadableSize(bytes_on_disk) AS size_on_disk
FROM system.parts
WHERE database = 'idz2'
  AND table = 'orders_ttl'
ORDER BY partition, name
FORMAT TabSeparatedWithNames;

ALTER TABLE idz2.orders_ttl
MODIFY TTL order_date + INTERVAL 90 DAY DELETE;

OPTIMIZE TABLE idz2.orders_ttl FINAL;

SELECT 'after_ttl' AS stage, count() AS rows_count
FROM idz2.orders_ttl
FORMAT TabSeparatedWithNames;

SELECT
    'after_ttl' AS stage,
    partition,
    name,
    active,
    rows,
    formatReadableSize(bytes_on_disk) AS size_on_disk
FROM system.parts
WHERE database = 'idz2'
  AND table = 'orders_ttl'
ORDER BY partition, name
FORMAT TabSeparatedWithNames;

SELECT
    order_id,
    order_date,
    product_name,
    category,
    line_total,
    order_status
FROM idz2.orders_ttl
ORDER BY order_id
FORMAT TabSeparatedWithNames;