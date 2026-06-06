CREATE DATABASE IF NOT EXISTS ha
ON CLUSTER production;

CREATE TABLE IF NOT EXISTS ha.metrics_local
ON CLUSTER production
(
    timestamp   DateTime,
    host        LowCardinality(String),
    metric_name LowCardinality(String),
    value       Float64
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/metrics_local',
    '{replica}'
)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (host, metric_name, timestamp);

CREATE TABLE IF NOT EXISTS ha.metrics_distributed
ON CLUSTER production
AS ha.metrics_local
ENGINE = Distributed(
    'production',
    'ha',
    'metrics_local',
    xxHash64(host)
);