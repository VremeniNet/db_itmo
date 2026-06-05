import subprocess
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
OUTPUT_FILE = CHECKS_DIR / "reshard_demo.txt"

MAIN_CONTAINER = "idz4-ch-s1-r1"
NEW_ROWS = 600_000

CLICKHOUSE_CONTAINERS = [
    "idz4-ch-s1-r1",
    "idz4-ch-s1-r2",
    "idz4-ch-s2-r1",
    "idz4-ch-s2-r2",
    "idz4-ch-s3-r1",
    "idz4-ch-s3-r2",
]


def run_command(command: list[str], input_text: str | None = None, timeout: int = 300) -> str:
    result = subprocess.run(
        command,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return result.stdout.strip()


def clickhouse_query(query: str, container: str = MAIN_CONTAINER, timeout: int = 300) -> str:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--multiquery",
        ],
        input_text=query,
        timeout=timeout,
    )


def add_section(lines: list[str], title: str) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)


def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    lines = []
    lines.append("Third shard and resharding demo")
    lines.append("")
    lines.append(f"New rows inserted after adding third shard: {NEW_ROWS}")

    add_section(lines, "Cluster 3x2 info")
    lines.append(clickhouse_query(
        """
SELECT
    cluster,
    shard_num,
    replica_num,
    host_name,
    port
FROM system.clusters
WHERE cluster = 'cluster_3x2'
ORDER BY
    shard_num,
    replica_num
FORMAT TabSeparatedWithNames;
"""
    ))

    ddl_sql = """
CREATE DATABASE IF NOT EXISTS idz4 ON CLUSTER cluster_3x2;

CREATE TABLE IF NOT EXISTS idz4.events_local ON CLUSTER cluster_3x2 (
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

DROP TABLE IF EXISTS idz4.events_distributed ON CLUSTER cluster_2x2;
DROP TABLE IF EXISTS idz4.events_distributed ON CLUSTER cluster_3x2;

CREATE TABLE idz4.events_distributed ON CLUSTER cluster_3x2
AS idz4.events_local
ENGINE = Distributed(
    'cluster_3x2',
    'idz4',
    'events_local',
    xxHash64(user_id)
);
"""
    add_section(lines, "Create local table on new shard and recreate Distributed table")
    lines.append(clickhouse_query(ddl_sql, timeout=600))

    insert_sql = f"""
SET insert_distributed_sync = 1;

INSERT INTO idz4.events_distributed
SELECT
    toDate('2025-01-01') + toIntervalDay(toUInt32(number % 30)) AS event_date,
    toDateTime(event_date) + toIntervalSecond(toUInt32(number % 86400)) AS event_time,
    toUInt64(900000000 + (number % 300000)) AS user_id,
    concat('reshard_session_', toString(intDiv(number, 5))) AS session_id,
    'reshard_test' AS event_type,
    concat('/reshard/page/', toString(number % 1000)) AS page_url,
    toUInt32(100 + (number % 5000)) AS duration_ms
FROM numbers({NEW_ROWS});

SYSTEM FLUSH DISTRIBUTED idz4.events_distributed;
"""
    add_section(lines, "Insert new data through events_distributed after adding third shard")
    lines.append(clickhouse_query(insert_sql, timeout=600))

    add_section(lines, "Sync replicas")
    for container in CLICKHOUSE_CONTAINERS:
        lines.append(f"[{container}]")
        lines.append(clickhouse_query(
            "SYSTEM SYNC REPLICA idz4.events_local;",
            container=container,
            timeout=300,
        ))
        lines.append("")

    check_sql = """
SELECT 'TOTAL THROUGH DISTRIBUTED TABLE' AS section
FORMAT TabSeparatedWithNames;

SELECT
    count() AS total_rows,
    countIf(event_type = 'reshard_test') AS new_rows
FROM idz4.events_distributed
FORMAT TabSeparatedWithNames;

SELECT 'ALL REPLICAS, OLD AND NEW DATA' AS section
FORMAT TabSeparatedWithNames;

SELECT
    hostName() AS host,
    count() AS total_rows,
    countIf(event_type = 'reshard_test') AS new_rows,
    countIf(event_type != 'reshard_test') AS old_rows
FROM clusterAllReplicas('cluster_3x2', idz4.events_local)
GROUP BY host
ORDER BY host
FORMAT TabSeparatedWithNames;

SELECT 'NEW DATA DISTRIBUTION BY SHARD REPLICAS' AS section
FORMAT TabSeparatedWithNames;

SELECT
    hostName() AS host,
    count() AS new_rows,
    uniqExact(user_id) AS unique_users
FROM clusterAllReplicas('cluster_3x2', idz4.events_local)
WHERE event_type = 'reshard_test'
GROUP BY host
ORDER BY host
FORMAT TabSeparatedWithNames;

SELECT 'OLD DATA ON THIRD SHARD' AS section
FORMAT TabSeparatedWithNames;

SELECT
    hostName() AS host,
    countIf(event_type != 'reshard_test') AS old_rows
FROM clusterAllReplicas('cluster_3x2', idz4.events_local)
WHERE hostName() IN ('ch-s3-r1', 'ch-s3-r2')
GROUP BY host
ORDER BY host
FORMAT TabSeparatedWithNames;
"""
    add_section(lines, "Distribution after adding third shard")
    lines.append(clickhouse_query(check_sql, timeout=300))

    lines.append("")
    lines.append("Conclusion:")
    lines.append("New rows inserted after changing the Distributed table were routed to 3 shards.")
    lines.append("Old rows were not moved automatically to the new shard.")
    lines.append("To rebalance old data, a separate migration is required: copy data into a new table with the new sharding key and then switch reads to it, or move partitions manually.")

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()