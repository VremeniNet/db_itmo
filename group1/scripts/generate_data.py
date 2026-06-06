import subprocess
import time
from pathlib import Path


ROWS_COUNT = 5_000_000

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT_DIR / "checks" / "data_distribution.txt"

MAIN_CONTAINER = "group1-ch-s1-r1"

CLICKHOUSE_NODES = [
    "group1-ch-s1-r1",
    "group1-ch-s1-r2",
    "group1-ch-s2-r1",
    "group1-ch-s2-r2",
]

PRIMARY_REPLICAS = [
    "group1-ch-s1-r1",
    "group1-ch-s2-r1",
]

SAMPLE_HOSTS = [
    "host-000001",
    "host-000002",
    "host-000003",
    "host-001000",
    "host-010000",
    "host-099999",
]


def run_command(
    command: list[str],
    input_text: str | None = None,
    timeout: int = 900,
) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )

    output = result.stdout.strip()

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {result.returncode}:\n"
            f"{' '.join(command)}\n\n{output}"
        )

    return output


def clickhouse_query(
    container: str,
    query: str,
    multiquery: bool = False,
    timeout: int = 900,
) -> str:
    command = [
        "docker",
        "exec",
        "-i",
        container,
        "clickhouse-client",
    ]

    if multiquery:
        command.append("--multiquery")
        return run_command(command, input_text=query, timeout=timeout)

    command.extend(["--query", query])
    return run_command(command, timeout=timeout)


def add_section(lines: list[str], title: str, content: str = "") -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)

    if content:
        lines.append(content)

    lines.append("")


def get_local_count(container: str) -> int:
    output = clickhouse_query(
        container,
        """
SELECT count()
FROM ha.metrics_local
FORMAT TabSeparatedRaw
""",
    )

    return int(output.strip())


def main() -> None:
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    lines: list[str] = []

    lines.append("ClickHouse HA telemetry data generation")
    lines.append("")
    lines.append(f"Rows requested: {ROWS_COUNT}")

    truncate_sql = """
TRUNCATE TABLE ha.metrics_local
ON CLUSTER production
SYNC;
"""

    add_section(lines, "Clean existing telemetry data")

    truncate_output = clickhouse_query(
        MAIN_CONTAINER,
        truncate_sql,
        multiquery=True,
    )

    lines.append(truncate_output or "Tables were truncated successfully.")

    insert_sql = f"""
SET insert_distributed_sync = 1;

INSERT INTO ha.metrics_distributed
SELECT
    toDateTime('2025-01-01 00:00:00')
        + toIntervalSecond(number % 2592000) AS timestamp,

    concat(
        'host-',
        leftPad(toString(number % 100000), 6, '0')
    ) AS host,

    multiIf(
        number % 5 = 0, 'cpu_usage',
        number % 5 = 1, 'memory_usage',
        number % 5 = 2, 'disk_usage',
        number % 5 = 3, 'network_in',
        'network_out'
    ) AS metric_name,

    multiIf(
        number % 5 = 0,
            toFloat64(number % 10000) / 100,

        number % 5 = 1,
            toFloat64(2000 + number % 14000) / 100,

        number % 5 = 2,
            toFloat64(1000 + number % 9000) / 100,

        number % 5 = 3,
            toFloat64(number % 500000) / 10,

        toFloat64(number % 400000) / 10
    ) AS value

FROM numbers({ROWS_COUNT});

SYSTEM FLUSH DISTRIBUTED ha.metrics_distributed;
"""

    add_section(lines, "Insert data through metrics_distributed")

    started_at = time.perf_counter()

    insert_output = clickhouse_query(
        MAIN_CONTAINER,
        insert_sql,
        multiquery=True,
        timeout=1200,
    )

    insert_elapsed = time.perf_counter() - started_at

    lines.append(insert_output or "Insert completed successfully.")
    lines.append(f"Insert elapsed time: {insert_elapsed:.3f} sec")

    add_section(lines, "Synchronize ReplicatedMergeTree replicas")

    for container in CLICKHOUSE_NODES:
        lines.append(f"[{container}]")

        sync_output = clickhouse_query(
            container,
            "SYSTEM SYNC REPLICA ha.metrics_local",
            timeout=600,
        )

        lines.append(sync_output or "Replica synchronized.")
        lines.append("")

    add_section(lines, "Global count through metrics_distributed")

    global_count_output = clickhouse_query(
        MAIN_CONTAINER,
        """
SELECT
    count() AS distributed_rows
FROM ha.metrics_distributed
FORMAT TabSeparatedWithNames
""",
    )

    lines.append(global_count_output)

    add_section(lines, "Local data on every ClickHouse node")

    local_status_query = """
SELECT
    hostName() AS node,
    count() AS rows,
    uniqExact(host) AS unique_hosts,
    min(timestamp) AS min_timestamp,
    max(timestamp) AS max_timestamp
FROM ha.metrics_local
FORMAT TabSeparatedWithNames
"""

    for container in CLICKHOUSE_NODES:
        lines.append(f"[{container}]")
        lines.append(clickhouse_query(container, local_status_query))
        lines.append("")

    shard_counts = [
        get_local_count(container)
        for container in PRIMARY_REPLICAS
    ]

    lines.append(
        "Sum of one replica from each shard: "
        f"{sum(shard_counts)}"
    )

    add_section(lines, "Replication status")

    replica_status_query = """
SELECT
    hostName() AS node,
    replica_name,
    is_leader,
    total_replicas,
    active_replicas,
    queue_size,
    inserts_in_queue,
    merges_in_queue,
    log_pointer,
    last_queue_update
FROM system.replicas
WHERE database = 'ha'
  AND table = 'metrics_local'
FORMAT TabSeparatedWithNames
"""

    for container in CLICKHOUSE_NODES:
        lines.append(f"[{container}]")
        lines.append(clickhouse_query(container, replica_status_query))
        lines.append("")

    sample_hosts_sql = ", ".join(
        f"'{host}'"
        for host in SAMPLE_HOSTS
    )

    sample_query = f"""
SELECT
    host,
    count() AS rows
FROM ha.metrics_local
WHERE host IN ({sample_hosts_sql})
GROUP BY host
ORDER BY host
FORMAT TabSeparatedWithNames
"""

    add_section(
        lines,
        "Check that one host is stored on one shard and both replicas",
    )

    for container in CLICKHOUSE_NODES:
        lines.append(f"[{container}]")
        lines.append(clickhouse_query(container, sample_query))
        lines.append("")

    analytics_query = """
SELECT
    metric_name,
    count() AS measurements,
    round(avg(value), 2) AS avg_value,
    round(min(value), 2) AS min_value,
    round(max(value), 2) AS max_value
FROM ha.metrics_distributed
GROUP BY metric_name
ORDER BY metric_name
FORMAT TabSeparatedWithNames
"""

    add_section(lines, "Analytical query through Distributed")

    lines.append(
        clickhouse_query(
            MAIN_CONTAINER,
            analytics_query,
            timeout=600,
        )
    )

    lines.append("")
    lines.append("Expected conditions:")
    lines.append("- distributed_rows = 5000000")
    lines.append("- sum of one replica from each shard = 5000000")
    lines.append("- replicas inside one shard have equal row counts")
    lines.append("- active_replicas = 2")
    lines.append("- queue_size = 0")
    lines.append("- each sample host exists only on one shard")
    lines.append("- the same host exists on both replicas of that shard")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))


if __name__ == "__main__":
    main()