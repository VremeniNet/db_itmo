
SELECT
    cluster,
    shard_num,
    replica_num,
    host_name,
    port
FROM system.clusters
WHERE cluster = 'production'
ORDER BY
    shard_num,
    replica_num;



SELECT
    count() AS distributed_rows
FROM ha.metrics_distributed;



SELECT
    metric_name,
    count() AS measurements,
    round(avg(value), 2) AS avg_value,
    round(min(value), 2) AS min_value,
    round(max(value), 2) AS max_value
FROM ha.metrics_distributed
GROUP BY metric_name
ORDER BY metric_name;



SELECT
    host,
    round(avg(value), 2) AS avg_cpu
FROM ha.metrics_distributed
WHERE metric_name = 'cpu_usage'
GROUP BY host
ORDER BY avg_cpu DESC
LIMIT 10;