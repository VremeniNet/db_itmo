import subprocess
import time
from pathlib import Path


NEW_ROWS = 1_000_000

ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"

EXPERIMENT_A_FILE = CHECKS_DIR / "experiment_a.txt"
REPLICATION_QUEUE_FILE = CHECKS_DIR / "replication_queue.txt"


def run_command(command: list[str], timeout: int = 120) -> str:
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


def docker(command: list[str], timeout: int = 120) -> str:
    return run_command(["docker", *command], timeout=timeout)


def append_section(lines: list[str], title: str, content: str) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)
    lines.append(content)
    lines.append("")


def get_counts() -> str:
    query = """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_a') AS experiment_a_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
"""
    parts = []
    for container in ["idz3-ch1", "idz3-ch2", "idz3-ch3"]:
        parts.append(f"[{container}]")
        parts.append(ch_query(container, query))
        parts.append("")
    return "\n".join(parts)


def wait_for_replica(container: str, expected_experiment_rows: int, timeout_seconds: int = 60) -> str:
    query = """
SELECT
    countIf(event_type = 'experiment_a') AS experiment_a_rows
FROM idz3.events
FORMAT TabSeparatedRaw
"""
    start = time.time()

    while time.time() - start < timeout_seconds:
        output = ch_query(container, query)

        try:
            current_rows = int(output.strip())
        except ValueError:
            current_rows = -1

        if current_rows >= expected_experiment_rows:
            return f"{container} synchronized: experiment_a_rows = {current_rows}"

        time.sleep(2)

    return f"{container} did not reach expected rows within timeout. Last output: {output}"


def wait_for_queue_zero(container: str, timeout_seconds: int = 60) -> str:
    query = """
SELECT
    queue_size
FROM system.replicas
WHERE database = 'idz3'
  AND table = 'events'
FORMAT TabSeparatedRaw
"""
    start = time.time()

    while time.time() - start < timeout_seconds:
        output = ch_query(container, query)

        try:
            queue_size = int(output.strip())
        except ValueError:
            queue_size = -1

        if queue_size == 0:
            return f"{container} queue_size = 0"

        time.sleep(2)

    return f"{container} queue was not empty within timeout. Last output: {output}"

def wait_for_clickhouse(container: str, timeout_seconds: int = 60) -> str:
    start = time.time()

    while time.time() - start < timeout_seconds:
        output = ch_query(container, "SELECT 1 FORMAT TabSeparatedRaw")

        if output.strip() == "1":
            return f"{container} is ready"

        time.sleep(2)

    return f"{container} did not become ready within timeout. Last output: {output}"

def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    lines = []
    lines.append("Experiment A — replica 3 failure and recovery")
    lines.append("")
    lines.append(f"New rows inserted during experiment: {NEW_ROWS}")

    append_section(lines, "Initial containers", docker(["ps", "--format", "table {{.Names}}\t{{.Status}}"]))

    append_section(lines, "Initial row counts", get_counts())

    append_section(lines, "Stop replica ch3", docker(["stop", "idz3-ch3"]))

    insert_query = f"""
INSERT INTO idz3.events
SELECT
    now() + toIntervalSecond(number) AS event_time,
    'experiment_a' AS event_type,
    toUInt64(1000000 + (number % 10000)) AS user_id,
    concat('experiment_a_payload_', toString(number)) AS payload
FROM numbers({NEW_ROWS})
"""
    append_section(lines, "Insert new data into ch1 while ch3 is stopped", ch_query("idz3-ch1", insert_query, timeout=180))

    append_section(lines, "Counts on ch1 and ch2 while ch3 is stopped", "\n".join([
        "[idz3-ch1]",
        ch_query(
            "idz3-ch1",
            """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_a') AS experiment_a_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
""",
        ),
        "",
        "[idz3-ch2]",
        ch_query(
            "idz3-ch2",
            """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_a') AS experiment_a_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
""",
        ),
    ]))

    append_section(lines, "Start replica ch3", docker(["start", "idz3-ch3"]))

    append_section(lines, "Wait for ch3 ClickHouse server", wait_for_clickhouse("idz3-ch3", timeout_seconds=90))

    stop_queue_output = ch_query("idz3-ch3", "SYSTEM STOP REPLICATION QUEUES idz3.events")
    append_section(lines, "Stop replication queue on ch3 to capture it", stop_queue_output)

    queue_query = """
SELECT *
FROM system.replication_queue
WHERE database = 'idz3'
  AND table = 'events'
FORMAT Vertical
"""
    queue_output = ch_query("idz3-ch3", queue_query)
    if not queue_output.strip():
        queue_output = "Replication queue was already empty when it was captured."

    REPLICATION_QUEUE_FILE.write_text(
        "system.replication_queue during experiment A\n\n" + queue_output + "\n",
        encoding="utf-8",
    )

    append_section(lines, "Captured system.replication_queue on ch3", queue_output)

    start_queue_output = ch_query("idz3-ch3", "SYSTEM START REPLICATION QUEUES idz3.events")
    append_section(lines, "Start replication queue on ch3", start_queue_output)

    append_section(lines, "Wait for ch3 to receive experiment data", wait_for_replica("idz3-ch3", NEW_ROWS, timeout_seconds=120))

    append_section(lines, "Wait for ch3 queue_size = 0", wait_for_queue_zero("idz3-ch3", timeout_seconds=120))

    append_section(lines, "Final row counts", get_counts())

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
    append_section(lines, "Final system.replicas from ch3", ch_query("idz3-ch3", replicas_query))

    EXPERIMENT_A_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()