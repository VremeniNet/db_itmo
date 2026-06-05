import subprocess
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
OUTPUT_FILE = CHECKS_DIR / "distributed_queries.txt"

MAIN_CONTAINER = "idz4-ch-s1-r1"

CLICKHOUSE_CONTAINERS = [
    "idz4-ch-s1-r1",
    "idz4-ch-s1-r2",
    "idz4-ch-s2-r1",
    "idz4-ch-s2-r2",
]


def run_command(command: list[str], input_text: str | None = None, timeout: int = 300) -> tuple[str, float]:
    start = time.perf_counter()

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

    elapsed = time.perf_counter() - start
    return result.stdout.strip(), elapsed


def run_multiquery(sql: str, container: str = MAIN_CONTAINER, timeout: int = 300) -> tuple[str, float]:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--multiquery",
        ],
        input_text=sql,
        timeout=timeout,
    )


def run_query(sql: str, container: str = MAIN_CONTAINER, timeout: int = 300) -> tuple[str, float]:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--query",
            sql,
        ],
        timeout=timeout,
    )


def add_section(lines: list[str], title: str) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)


def add_query_result(lines: list[str], title: str, sql: str, timeout: int = 300) -> None:
    add_section(lines, title)
    lines.append("SQL:")
    lines.append(sql.strip())
    lines.append("")
    output, elapsed = run_query(sql, timeout=timeout)
    lines.append("Result:")
    lines.append(output)
    lines.append("")
    lines.append(f"Elapsed time: {elapsed:.3f} sec")


def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    lines = []
    lines.append("Distributed queries check")
    lines.append("")

    user_dict_sql = (ROOT_DIR / "sql" / "03_user_dict.sql").read_text(encoding="utf-8")

    add_section(lines, "Create and load user_dict")
    output, elapsed = run_multiquery(user_dict_sql, timeout=600)
    lines.append(output)
    lines.append("")
    lines.append(f"Elapsed time: {elapsed:.3f} sec")

    add_section(lines, "Sync user_dict replicas")
    for container in CLICKHOUSE_CONTAINERS:
        output, elapsed = run_query(
            "SYSTEM SYNC REPLICA idz4.user_dict",
            container=container,
            timeout=300,
        )
        lines.append(f"[{container}]")
        lines.append(output)
        lines.append(f"Elapsed time: {elapsed:.3f} sec")
        lines.append("")

    add_query_result(
        lines,
        "1. Global COUNT through events_distributed",
        """
SELECT
    count() AS distributed_count
FROM idz4.events_distributed
FORMAT TabSeparatedWithNames
""",
    )

    add_section(lines, "1. Local shard counts")
    shard_counts = []
    for container in ["idz4-ch-s1-r1", "idz4-ch-s2-r1"]:
        sql = "SELECT hostName() AS host, count() AS rows FROM idz4.events_local FORMAT TabSeparatedWithNames"
        output, elapsed = run_query(sql, container=container)
        lines.append(f"[{container}]")
        lines.append(output)
        lines.append(f"Elapsed time: {elapsed:.3f} sec")
        lines.append("")

        raw_output, _ = run_query("SELECT count() FROM idz4.events_local FORMAT TabSeparatedRaw", container=container)
        shard_counts.append(int(raw_output.strip()))

    lines.append(f"Local shard sum: {sum(shard_counts)}")

    add_query_result(
        lines,
        "2. GROUP BY with sharding key: top-10 users by event count",
        """
SELECT
    user_id,
    count() AS events_count,
    sum(duration_ms) AS total_duration_ms
FROM idz4.events_distributed
GROUP BY user_id
ORDER BY
    events_count DESC,
    user_id
LIMIT 10
FORMAT TabSeparatedWithNames
""",
        timeout=300,
    )

    add_query_result(
        lines,
        "3. GROUP BY without sharding key: top-10 pages by visits",
        """
SELECT
    page_url,
    count() AS visits,
    uniqExact(user_id) AS users_count,
    round(avg(duration_ms), 2) AS avg_duration_ms
FROM idz4.events_distributed
GROUP BY page_url
ORDER BY
    visits DESC,
    page_url
LIMIT 10
FORMAT TabSeparatedWithNames
""",
        timeout=300,
    )

    add_query_result(
        lines,
        "4. JOIN events_distributed with local replicated user_dict",
        """
SELECT
    u.segment,
    count() AS events_count,
    uniqExact(e.user_id) AS users_count,
    round(avg(e.duration_ms), 2) AS avg_duration_ms
FROM idz4.events_distributed AS e
INNER JOIN idz4.user_dict AS u
    ON e.user_id = u.user_id
GROUP BY u.segment
ORDER BY events_count DESC
FORMAT TabSeparatedWithNames
""",
        timeout=300,
    )

    add_query_result(
        lines,
        "5. GLOBAL IN example for vip users",
        """
SELECT
    count() AS vip_events
FROM idz4.events_distributed
WHERE user_id GLOBAL IN (
    SELECT user_id
    FROM idz4.user_dict_distributed
    WHERE segment = 'vip'
)
FORMAT TabSeparatedWithNames
""",
        timeout=300,
    )

    lines.append("")
    lines.append("Notes:")
    lines.append("- GROUP BY user_id is efficient because user_id is the sharding key.")
    lines.append("- GROUP BY page_url is not aligned with the sharding key, so partial aggregates from different shards have to be merged.")
    lines.append("- user_dict is sharded by the same user_id key, so the JOIN can be executed with colocated data.")
    lines.append("- GLOBAL IN builds a set once and sends it to shards, which is useful when a small reference set must be broadcast.")

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()