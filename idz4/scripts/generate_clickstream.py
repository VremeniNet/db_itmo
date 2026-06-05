import subprocess
from pathlib import Path


CONTAINER_NAME = "idz4-ch-s1-r1"

CLICKHOUSE_CONTAINERS = [
    "idz4-ch-s1-r1",
    "idz4-ch-s1-r2",
    "idz4-ch-s2-r1",
    "idz4-ch-s2-r2",
]

ROWS_COUNT = 2_000_000

ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
OUTPUT_FILE = CHECKS_DIR / "data_distribution.txt"


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


def clickhouse_query(query: str, timeout: int = 300) -> str:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER_NAME,
            "clickhouse-client",
            "--multiquery",
        ],
        input_text=query,
        timeout=timeout,
    )

def clickhouse_query_on(container_name: str, query: str, timeout: int = 300) -> str:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container_name,
            "clickhouse-client",
            "--multiquery",
        ],
        input_text=query,
        timeout=timeout,
    )


def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    insert_sql = f"""
SET insert_distributed_sync = 1;
TRUNCATE TABLE idz4.events_local ON CLUSTER cluster_2x2 SYNC;

INSERT INTO idz4.events_distributed
SELECT
    toDate('2024-01-01') + toIntervalDay(toUInt32(number % 365)) AS event_date,
    toDateTime(event_date) + toIntervalSecond(toUInt32(number % 86400)) AS event_time,
    toUInt64(number % 500000) AS user_id,
    concat('session_', toString(intDiv(number, 5))) AS session_id,
    multiIf(
        number % 5 = 0, 'page_view',
        number % 5 = 1, 'click',
        number % 5 = 2, 'scroll',
        number % 5 = 3, 'purchase',
        'logout'
    ) AS event_type,
    concat('/page/', toString(number % 1000)) AS page_url,
    toUInt32(100 + (number % 10000)) AS duration_ms
FROM numbers({ROWS_COUNT});
"""

    check_sql = """
SELECT 'TOTAL THROUGH DISTRIBUTED TABLE' AS section
FORMAT TabSeparatedWithNames;

SELECT
    count() AS total_rows
FROM idz4.events_distributed
FORMAT TabSeparatedWithNames;

SELECT 'ROWS ON EACH REPLICA' AS section
FORMAT TabSeparatedWithNames;

SELECT
    hostName() AS host,
    count() AS rows
FROM idz4.events_local
FORMAT TabSeparatedWithNames;

SELECT 'ROWS ON CLUSTER' AS section
FORMAT TabSeparatedWithNames;

SELECT
    hostName() AS host,
    count() AS rows
FROM clusterAllReplicas('cluster_2x2', idz4.events_local)
GROUP BY host
ORDER BY host
FORMAT TabSeparatedWithNames;

SELECT 'USER DISTRIBUTION ON CLUSTER' AS section
FORMAT TabSeparatedWithNames;

SELECT
    hostName() AS host,
    uniqExact(user_id) AS unique_users,
    count() AS rows
FROM clusterAllReplicas('cluster_2x2', idz4.events_local)
GROUP BY host
ORDER BY host
FORMAT TabSeparatedWithNames;

SELECT 'CHECK THAT ONE USER_ID IS STORED ON ONE SHARD' AS section
FORMAT TabSeparatedWithNames;

SELECT
    user_id,
    groupArray(host) AS hosts,
    count() AS rows
FROM
(
    SELECT
        hostName() AS host,
        user_id,
        count() AS rows_on_host
    FROM clusterAllReplicas('cluster_2x2', idz4.events_local)
    WHERE user_id IN (1, 2, 3, 100, 1000, 7777)
    GROUP BY
        host,
        user_id
)
GROUP BY user_id
ORDER BY user_id
FORMAT TabSeparatedWithNames;
"""

    output = []
    output.append("Clickstream data generation and distribution check")
    output.append("")
    output.append(f"Rows requested: {ROWS_COUNT}")
    output.append("")

    output.append("=" * 80)
    output.append("Insert data through events_distributed")
    output.append("=" * 80)
    output.append(clickhouse_query(insert_sql, timeout=600))
    output.append("")

    output.append("=" * 80)
    output.append("Sync replicas")
    output.append("=" * 80)

    for container in CLICKHOUSE_CONTAINERS:
        output.append(f"[{container}]")
        output.append(
        clickhouse_query_on(
            container,
            "SYSTEM SYNC REPLICA idz4.events_local;",
            timeout=300,
        )
    )
    output.append("")

    output.append("=" * 80)
    output.append("Distribution checks")
    output.append("=" * 80)
    output.append(clickhouse_query(check_sql, timeout=300))
    output.append("")

    OUTPUT_FILE.write_text("\n".join(output), encoding="utf-8")
    print("\n".join(output))


if __name__ == "__main__":
    main()