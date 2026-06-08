CREATE DATABASE IF NOT EXISTS ecommerce
ON CLUSTER cluster_2x2;

CREATE TABLE IF NOT EXISTS ecommerce.orders_analytics_local
ON CLUSTER cluster_2x2
(
    order_date      Date,
    order_id        UInt64,
    customer_name   String,
    region          LowCardinality(String),
    product_name    String,
    category        LowCardinality(String),
    quantity        UInt32,
    price           Decimal(12, 2),
    line_total      Decimal(14, 2),
    order_status    LowCardinality(String)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/orders_analytics_local',
    '{replica}'
)
PARTITION BY toYYYYMM(order_date)
ORDER BY (
    category,
    order_date,
    order_id
);

CREATE TABLE IF NOT EXISTS ecommerce.orders_analytics_distributed
ON CLUSTER cluster_2x2
AS ecommerce.orders_analytics_local
ENGINE = Distributed(
    'cluster_2x2',
    'ecommerce',
    'orders_analytics_local',
    cityHash64(order_id)
);