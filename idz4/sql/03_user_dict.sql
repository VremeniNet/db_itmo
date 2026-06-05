CREATE DATABASE IF NOT EXISTS idz4 ON CLUSTER cluster_2x2;

DROP TABLE IF EXISTS idz4.user_dict_distributed ON CLUSTER cluster_2x2;
DROP TABLE IF EXISTS idz4.user_dict ON CLUSTER cluster_2x2;

CREATE TABLE idz4.user_dict ON CLUSTER cluster_2x2 (
    user_id UInt64,
    name    String,
    segment LowCardinality(String)
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/user_dict',
    '{replica}'
)
ORDER BY user_id;

CREATE TABLE idz4.user_dict_distributed ON CLUSTER cluster_2x2
AS idz4.user_dict
ENGINE = Distributed(
    'cluster_2x2',
    'idz4',
    'user_dict',
    xxHash64(user_id)
);

SET insert_distributed_sync = 1;

INSERT INTO idz4.user_dict_distributed
SELECT
    toUInt64(number) AS user_id,
    concat('user_', toString(number)) AS name,
    multiIf(
        number % 4 = 0, 'new',
        number % 4 = 1, 'regular',
        number % 4 = 2, 'vip',
        'inactive'
    ) AS segment
FROM numbers(500000);

SYSTEM FLUSH DISTRIBUTED idz4.user_dict_distributed;