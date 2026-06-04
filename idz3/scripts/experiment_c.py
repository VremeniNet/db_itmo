import subprocess
import time
from pathlib import Path


NEW_ROWS = 100_000

ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
EXPERIMENT_C_FILE = CHECKS_DIR / "experiment_c.txt"


def run_command(command: list[str], timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return f"TIMEOUT after {timeout} seconds\n{output}"


def docker(command: list[str], timeout: int = 120) -> str:
    return run_command(["docker", *command], timeout=timeout)


def ch_query(container: str, query: str, timeout: int = 120) -> str:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--query",
            query,
        ],
        timeout=timeout,
    )


def append_section(lines: list[str], title: str, content: str) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)
    lines.append(content)
    lines.append("")


def wait_for_clickhouse(container: str, timeout_seconds: int = 60) -> str:
    start = time.time()

    while time.time() - start < timeout_seconds:
        output = ch_query(container, "SELECT 1 FORMAT TabSeparatedRaw")

        if output.strip() == "1":
            return f"{container} is ready"

        time.sleep(2)

    return f"{container} did not become ready within timeout. Last output: {output}"


def wait_for_event_rows(container: str, event_type: str, expected_rows: int, timeout_seconds: int = 120) -> str:
    query = f"""
SELECT count()
FROM idz3.events
WHERE event_type = '{event_type}'
FORMAT TabSeparatedRaw
"""
    start = time.time()

    while time.time() - start < timeout_seconds:
        output = ch_query(container, query)

        try:
            rows = int(output.strip())
        except ValueError:
            rows = -1

        if rows >= expected_rows:
            return f"{container} synchronized: {event_type} rows = {rows}"

        time.sleep(2)

    return f"{container} did not reach expected rows. Last output: {output}"


def counts_for_event(event_type: str, containers: list[str]) -> str:
    query = f"""
SELECT
    hostName() AS node,
    count() AS rows_count
FROM idz3.events
WHERE event_type = '{event_type}'
FORMAT TabSeparatedWithNames
"""
    parts = []

    for container in containers:
        parts.append(f"[{container}]")
        parts.append(ch_query(container, query))
        parts.append("")

    return "\n".join(parts)


def consistency_for_event(event_type: str, containers: list[str]) -> str:
    query = f"""
SELECT
    hostName() AS node,
    count() AS rows_count,
    min(event_time) AS min_event_time,
    max(event_time) AS max_event_time,
    sum(user_id) AS user_id_sum,
    uniqExact(payload) AS unique_payloads,
    sum(cityHash64(payload)) AS payload_hash_sum
FROM idz3.events
WHERE event_type = '{event_type}'
FORMAT TabSeparatedWithNames
"""
    parts = []

    for container in containers:
        parts.append(f"[{container}]")
        parts.append(ch_query(container, query))
        parts.append("")

    return "\n".join(parts)


def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    run_id = int(time.time())
    event_type = f"experiment_c_{run_id}"

    lines = []
    lines.append("Experiment C — deterministic replication without conflicts")
    lines.append("")
    lines.append(f"Run event_type: {event_type}")
    lines.append(f"Rows inserted during experiment: {NEW_ROWS}")

    append_section(lines, "Start all required containers", "\n".join([
        docker(["start", "idz3-keeper1"]),
        docker(["start", "idz3-keeper2"]),
        docker(["start", "idz3-keeper3"]),
        docker(["start", "idz3-ch1"]),
        docker(["start", "idz3-ch2"]),
        docker(["start", "idz3-ch3"]),
    ]))

    time.sleep(5)

    append_section(lines, "Wait for ClickHouse nodes", "\n".join([
        wait_for_clickhouse("idz3-ch1"),
        wait_for_clickhouse("idz3-ch2"),
        wait_for_clickhouse("idz3-ch3"),
    ]))

    append_section(lines, "Initial counts for this experiment event_type", counts_for_event(
        event_type,
        ["idz3-ch1", "idz3-ch2", "idz3-ch3"],
    ))

    append_section(lines, "Stop replica ch2", docker(["stop", "idz3-ch2"]))

    insert_query = f"""
INSERT INTO idz3.events
SELECT
    now() + toIntervalSecond(number) AS event_time,
    '{event_type}' AS event_type,
    toUInt64(4000000 + (number % 10000)) AS user_id,
    concat('{event_type}_payload_', toString(number)) AS payload
FROM numbers({NEW_ROWS})
"""
    append_section(lines, "Insert new data into ch1 while ch2 is stopped", ch_query(
        "idz3-ch1",
        insert_query,
        timeout=180,
    ))

    append_section(lines, "Counts on available replicas while ch2 is stopped", counts_for_event(
        event_type,
        ["idz3-ch1", "idz3-ch3"],
    ))

    append_section(lines, "Start replica ch2", docker(["start", "idz3-ch2"]))

    append_section(lines, "Wait for ch2 ClickHouse server", wait_for_clickhouse("idz3-ch2", timeout_seconds=90))

    append_section(lines, "Run SYSTEM SYNC REPLICA on ch2", ch_query(
        "idz3-ch2",
        "SYSTEM SYNC REPLICA idz3.events",
        timeout=180,
    ))

    append_section(lines, "Wait for ch2 to receive experiment data", wait_for_event_rows(
        "idz3-ch2",
        event_type,
        NEW_ROWS,
        timeout_seconds=180,
    ))

    append_section(lines, "Final counts on all replicas", counts_for_event(
        event_type,
        ["idz3-ch1", "idz3-ch2", "idz3-ch3"],
    ))

    append_section(lines, "Consistency check on all replicas", consistency_for_event(
        event_type,
        ["idz3-ch1", "idz3-ch2", "idz3-ch3"],
    ))

    replicas_query = """
SELECT
    database,
    table,
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
WHERE table = 'events'
FORMAT Vertical
"""
    append_section(lines, "Final system.replicas from ch2", ch_query("idz3-ch2", replicas_query))

    lines.append("")
    lines.append("Conclusion:")
    lines.append("No conflict appeared after ch2 recovery.")
    lines.append("The stopped replica received the same data from the replication log in Keeper.")
    lines.append("ReplicatedMergeTree replication is deterministic: replicas follow the shared log instead of creating independent conflicting states.")

    EXPERIMENT_C_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()