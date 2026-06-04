CREATE DATABASE IF NOT EXISTS idz3 ON CLUSTER idz3_cluster;

DROP TABLE IF EXISTS idz3.events ON CLUSTER idz3_cluster;

CREATE TABLE idz3.events ON CLUSTER idz3_cluster (
    event_time DateTime,
    event_type LowCardinality(String),
    user_id    UInt64,
    payload    String
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/events',
    '{replica}'
)
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_type, event_time);