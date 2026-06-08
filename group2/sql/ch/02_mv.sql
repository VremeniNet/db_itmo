CREATE TABLE IF NOT EXISTS ecommerce.category_revenue_local
ON CLUSTER cluster_2x2
(
    order_date Date,
    category   LowCardinality(String),
    revenue    AggregateFunction(sum, Float64),
    quantity   AggregateFunction(sum, UInt64)
)
ENGINE = ReplicatedAggregatingMergeTree(
    '/clickhouse/tables/{shard}/category_revenue_local',
    '{replica}'
)
PARTITION BY toYYYYMM(order_date)
ORDER BY (
    category,
    order_date
);

CREATE TABLE IF NOT EXISTS ecommerce.category_revenue_distributed
ON CLUSTER cluster_2x2
AS ecommerce.category_revenue_local
ENGINE = Distributed(
    'cluster_2x2',
    'ecommerce',
    'category_revenue_local',
    cityHash64(category)
);

CREATE MATERIALIZED VIEW IF NOT EXISTS ecommerce.mv_category_revenue
ON CLUSTER cluster_2x2
TO ecommerce.category_revenue_local
AS
SELECT
    order_date,
    category,
    sumState(toFloat64(line_total)) AS revenue,
    sumState(toUInt64(quantity)) AS quantity
FROM ecommerce.orders_analytics_local
GROUP BY
    order_date,
    category;


CREATE TABLE IF NOT EXISTS ecommerce.daily_orders_local
ON CLUSTER cluster_2x2
(
    order_date   Date,
    orders_count AggregateFunction(uniqExact, UInt64),
    revenue      AggregateFunction(sum, Float64)
)
ENGINE = ReplicatedAggregatingMergeTree(
    '/clickhouse/tables/{shard}/daily_orders_local',
    '{replica}'
)
PARTITION BY toYYYYMM(order_date)
ORDER BY order_date;

CREATE TABLE IF NOT EXISTS ecommerce.daily_orders_distributed
ON CLUSTER cluster_2x2
AS ecommerce.daily_orders_local
ENGINE = Distributed(
    'cluster_2x2',
    'ecommerce',
    'daily_orders_local',
    cityHash64(order_date)
);

CREATE MATERIALIZED VIEW IF NOT EXISTS ecommerce.mv_daily_orders
ON CLUSTER cluster_2x2
TO ecommerce.daily_orders_local
AS
SELECT
    order_date,
    uniqExactState(order_id) AS orders_count,
    sumState(toFloat64(line_total)) AS revenue
FROM ecommerce.orders_analytics_local
GROUP BY order_date;