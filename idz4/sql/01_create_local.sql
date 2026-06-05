CREATE DATABASE IF NOT EXISTS idz4 ON CLUSTER cluster_2x2;

DROP TABLE IF EXISTS idz4.events_distributed ON CLUSTER cluster_2x2;
DROP TABLE IF EXISTS idz4.events_local ON CLUSTER cluster_2x2;

CREATE TABLE idz4.events_local ON CLUSTER cluster_2x2 (
    event_date  Date,
    event_time  DateTime,
    user_id     UInt64,
    session_id  String,
    event_type  LowCardinality(String),
    page_url    String,
    duration_ms UInt32
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/events_local',
    '{replica}'
)
PARTITION BY toYYYYMM(event_date)
ORDER BY (user_id, event_time);