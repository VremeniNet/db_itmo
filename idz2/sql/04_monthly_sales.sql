CREATE DATABASE IF NOT EXISTS idz2;

DROP TABLE IF EXISTS idz2.monthly_sales;

CREATE TABLE idz2.monthly_sales (
    month         Date,
    category      LowCardinality(String),
    region        LowCardinality(String),
    total_qty     UInt64,
    total_revenue Decimal(18, 2)
)
ENGINE = SummingMergeTree((total_qty, total_revenue))
PARTITION BY toYYYYMM(month)
ORDER BY (month, category, region);