import socket
import subprocess
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT_DIR / "checks" / "fault_scenarios.txt"

FAULT_RUN_ID = int(time.time())

FAULT_ZK_PATH = (
    f"/clickhouse/tables/{{shard}}/"
    f"fault_test_local_{FAULT_RUN_ID}"
)

MAIN_NODE = "group1-ch-s1-r1"

CLICKHOUSE_NODES = [
    "group1-ch-s1-r1",
    "group1-ch-s1-r2",
    "group1-ch-s2-r1",
    "group1-ch-s2-r2",
]

SHARD_2_NODES = [
    "group1-ch-s2-r1",
    "group1-ch-s2-r2",
]

KEEPER_NODES = [
    "group1-keeper1",
    "group1-keeper2",
    "group1-keeper3",
]

KEEPER_ENDPOINTS = [
    ("keeper1", "127.0.0.1", 9481),
    ("keeper2", "127.0.0.1", 9482),
    ("keeper3", "127.0.0.1", 9483),
]


def run_command(
    command: list[str],
    timeout: int = 120,
    check: bool = True,
    input_text: str | None = None,
) -> tuple[int, str]:
    try:
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
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""

        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")

        return 124, (
            f"TIMEOUT after {timeout} seconds\n"
            f"{output.strip()}"
        )

    output = result.stdout.strip()

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {result.returncode}:\n"
            f"{' '.join(command)}\n\n"
            f"{output}"
        )

    return result.returncode, output


def docker(
    arguments: list[str],
    timeout: int = 120,
    check: bool = True,
) -> tuple[int, str]:
    return run_command(
        ["docker", *arguments],
        timeout=timeout,
        check=check,
    )


def clickhouse_query(
    container: str,
    query: str,
    timeout: int = 120,
    check: bool = True,
) -> tuple[int, str]:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--receive_timeout=10",
            "--send_timeout=10",
            "--query",
            query,
        ],
        timeout=timeout,
        check=check,
    )

def clickhouse_query_with_id(
    container: str,
    query: str,
    query_id: str,
    timeout: int = 120,
    check: bool = True,
) -> tuple[int, str]:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--receive_timeout=10",
            "--send_timeout=10",
            "--query_id",
            query_id,
            "--query",
            query,
        ],
        timeout=timeout,
        check=check,
    )


def clickhouse_multiquery(
    container: str,
    query: str,
    timeout: int = 300,
    check: bool = True,
) -> tuple[int, str]:
    return run_command(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--receive_timeout=20",
            "--send_timeout=20",
            "--multiquery",
        ],
        input_text=query,
        timeout=timeout,
        check=check,
    )


def wait_for_clickhouse(
    container: str,
    timeout_seconds: int = 90,
) -> str:
    started_at = time.time()
    last_output = ""

    while time.time() - started_at < timeout_seconds:
        code, output = clickhouse_query(
            container,
            "SELECT 1 FORMAT TabSeparatedRaw",
            timeout=10,
            check=False,
        )

        last_output = output

        if code == 0 and output.strip() == "1":
            return f"{container} is ready"

        time.sleep(2)

    raise RuntimeError(
        f"{container} did not become ready. "
        f"Last output: {last_output}"
    )

def wait_for_replica_ready(
    container: str,
    table: str = "fault_test_local",
    timeout_seconds: int = 120,
) -> str:
    started_at = time.time()
    last_output = ""

    query = f"""
SELECT
    is_readonly,
    active_replicas,
    queue_size
FROM system.replicas
WHERE database = 'ha'
  AND table = '{table}'
FORMAT TabSeparatedRaw
"""

    while time.time() - started_at < timeout_seconds:
        code, output = clickhouse_query(
            container,
            query,
            timeout=15,
            check=False,
        )

        last_output = output.strip()

        if code == 0 and last_output:
            values = last_output.split("\t")

            if len(values) >= 3:
                is_readonly = values[0]
                active_replicas = values[1]

                if is_readonly == "0" and active_replicas == "2":
                    return (
                        f"{container}: replica is writable, "
                        f"active_replicas={active_replicas}, "
                        f"queue_size={values[2]}"
                    )

        time.sleep(2)

    raise RuntimeError(
        f"{container}: replica did not become ready. "
        f"Last output: {last_output}"
    )

def start_and_wait_clickhouse(container: str) -> str:
    _, start_output = docker(
        ["start", container],
        check=False,
    )

    ready_output = wait_for_clickhouse(container)

    return "\n".join(
        item
        for item in [start_output, ready_output]
        if item
    )


def send_keeper_command(
    host: str,
    port: int,
    command: str,
) -> str:
    with socket.create_connection(
        (host, port),
        timeout=3,
    ) as connection:
        connection.sendall(
            (command + "\n").encode("utf-8")
        )
        connection.settimeout(3)

        chunks: list[bytes] = []

        while True:
            try:
                data = connection.recv(4096)
            except socket.timeout:
                break

            if not data:
                break

            chunks.append(data)

    return b"".join(chunks).decode(
        "utf-8",
        errors="replace",
    ).strip()


def keeper_health() -> str:
    lines: list[str] = []

    for name, host, port in KEEPER_ENDPOINTS:
        lines.append(f"[{name} {host}:{port}]")

        try:
            ruok = send_keeper_command(
                host,
                port,
                "ruok",
            )
            lines.append(f"ruok: {ruok}")
        except Exception as error:
            lines.append(f"ruok ERROR: {error}")

        try:
            mntr = send_keeper_command(
                host,
                port,
                "mntr",
            )

            state_lines = [
                line
                for line in mntr.splitlines()
                if (
                    "zk_server_state" in line
                    or "zk_synced_followers" in line
                )
            ]

            if state_lines:
                lines.extend(state_lines)
            else:
                lines.append("mntr: no state data")

        except Exception as error:
            lines.append(f"mntr ERROR: {error}")

        lines.append("")

    return "\n".join(lines)


def add_section(
    lines: list[str],
    title: str,
    content: str = "",
) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)

    if content:
        lines.append(content)

    lines.append("")


def setup_fault_tables() -> str:
    sql = f"""
DROP TABLE IF EXISTS ha.fault_test_distributed
ON CLUSTER production
SYNC;

DROP TABLE IF EXISTS ha.fault_test_local
ON CLUSTER production
SYNC;

CREATE TABLE ha.fault_test_local
ON CLUSTER production
(
    id         UInt64,
    scenario   LowCardinality(String),
    created_at DateTime
)
ENGINE = ReplicatedMergeTree(
    '{FAULT_ZK_PATH}',
    '{{replica}}'
)
ORDER BY id;

CREATE TABLE ha.fault_test_distributed
ON CLUSTER production
AS ha.fault_test_local
ENGINE = Distributed(
    'production',
    'ha',
    'fault_test_local',
    id
);
"""

    _, output = clickhouse_multiquery(
        MAIN_NODE,
        sql,
        timeout=300,
    )

    return (
        f"Keeper path: {FAULT_ZK_PATH}\n"
        f"{output or 'Fault-test tables created.'}"
    )


def cleanup_fault_tables() -> str:
    sql = """
DROP TABLE IF EXISTS ha.fault_test_distributed
ON CLUSTER production
SYNC;

DROP TABLE IF EXISTS ha.fault_test_local
ON CLUSTER production
SYNC;
"""

    code, output = clickhouse_multiquery(
        MAIN_NODE,
        sql,
        timeout=300,
        check=False,
    )

    if code == 0:
        return output or "Fault-test tables removed."

    return (
        f"Cleanup returned code {code}\n"
        f"{output}"
    )


def sync_fault_replicas() -> str:
    lines: list[str] = []

    for container in CLICKHOUSE_NODES:
        code, output = clickhouse_query(
            container,
            "SYSTEM SYNC REPLICA ha.fault_test_local",
            timeout=120,
            check=False,
        )

        lines.append(
            f"[{container}] code={code}"
        )
        lines.append(
            output or "Replica synchronized."
        )

    return "\n".join(lines)


def fault_table_counts() -> str:
    query = """
SELECT
    hostName() AS node,
    count() AS rows,
    countIf(scenario = 'one_keeper_down')
        AS one_keeper_down_rows,
    countIf(scenario = 'no_quorum')
        AS no_quorum_rows
FROM ha.fault_test_local
FORMAT TabSeparatedWithNames
"""

    lines: list[str] = []

    for container in CLICKHOUSE_NODES:
        code, output = clickhouse_query(
            container,
            query,
            timeout=60,
            check=False,
        )

        lines.append(f"[{container}] code={code}")
        lines.append(output)
        lines.append("")

    return "\n".join(lines)


def restore_all_services() -> str:
    lines: list[str] = []

    for container in [
        *KEEPER_NODES,
        *CLICKHOUSE_NODES,
    ]:
        _, output = docker(
            ["start", container],
            check=False,
        )

        if output:
            lines.append(output)

    for container in CLICKHOUSE_NODES:
        try:
            lines.append(
                wait_for_clickhouse(container)
            )
        except Exception as error:
            lines.append(
                f"{container} recovery ERROR: {error}"
            )

    return "\n".join(lines)


def main() -> None:
    lines: list[str] = []

    lines.append(
        "ClickHouse HA fault injection scenarios"
    )

    try:
        add_section(
            lines,
            "Restore all services before tests",
            restore_all_services(),
        )

        time.sleep(5)

        add_section(
            lines,
            "Create temporary replicated test tables",
            setup_fault_tables(),
        )

        # ------------------------------------------------------------
        # Сценарий 1: потеря целого шарда
        # ------------------------------------------------------------

        _, initial_count = clickhouse_query(
            MAIN_NODE,
            """
SELECT count() AS distributed_rows
FROM ha.metrics_distributed
FORMAT TabSeparatedWithNames
""",
        )

        add_section(
            lines,
            "Scenario 1 — initial distributed count",
            initial_count,
        )

        stopped_outputs: list[str] = []

        for container in SHARD_2_NODES:
            _, output = docker(
                ["stop", container]
            )
            stopped_outputs.append(output)

        add_section(
            lines,
            "Scenario 1 — stop shard 2",
            "\n".join(stopped_outputs),
        )

        time.sleep(3)

        _, local_shard1 = clickhouse_query(
            MAIN_NODE,
            """
SELECT
    hostName() AS node,
    count() AS local_rows
FROM ha.metrics_local
FORMAT TabSeparatedWithNames
""",
        )

        add_section(
            lines,
            "Scenario 1 — local SELECT on shard 1 still works",
            local_shard1,
        )

        distributed_code, distributed_output = (
            clickhouse_query(
                MAIN_NODE,
                """
SELECT count() AS distributed_rows
FROM ha.metrics_distributed
SETTINGS
    skip_unavailable_shards = 0,
    max_execution_time = 15
FORMAT TabSeparatedWithNames
""",
                timeout=30,
                check=False,
            )
        )

        add_section(
            lines,
            "Scenario 1 — Distributed query with shard 2 unavailable",
            (
                f"Return code: {distributed_code}\n"
                f"{distributed_output}"
            ),
        )

        recovered_outputs: list[str] = []

        for container in SHARD_2_NODES:
            recovered_outputs.append(
                start_and_wait_clickhouse(container)
            )

        add_section(
            lines,
            "Scenario 1 — restore shard 2",
            "\n".join(recovered_outputs),
        )

        replica_ready_outputs: list[str] = []

        for container in CLICKHOUSE_NODES:
            replica_ready_outputs.append(
                wait_for_replica_ready(container)
            )

        add_section(
            lines,
            "Scenario 1 — wait for fault-test replicas",
            "\n".join(replica_ready_outputs),
        )

        for container in CLICKHOUSE_NODES:
            clickhouse_query(
                container,
                "SYSTEM SYNC REPLICA ha.metrics_local",
                timeout=180,
                check=False,
            )

        _, restored_count = clickhouse_query(
            MAIN_NODE,
            """
SELECT count() AS distributed_rows
FROM ha.metrics_distributed
FORMAT TabSeparatedWithNames
""",
        )

        add_section(
            lines,
            "Scenario 1 — distributed count after recovery",
            restored_count,
        )

        # ------------------------------------------------------------
        # Сценарий 2: потеря одного Keeper
        # ------------------------------------------------------------

        for keeper in KEEPER_NODES:
            docker(
                ["start", keeper],
                check=False,
            )

        time.sleep(5)

        add_section(
            lines,
            "Scenario 2 — initial Keeper health",
            keeper_health(),
        )

        _, stop_keeper1 = docker(
            ["stop", "group1-keeper1"]
        )

        add_section(
            lines,
            "Scenario 2 — stop keeper1",
            stop_keeper1,
        )

        time.sleep(5)

        add_section(
            lines,
            "Scenario 2 — Keeper health with one node down",
            keeper_health(),
        )

        insert_one_keeper_sql = """
SET insert_distributed_sync = 1;

INSERT INTO ha.fault_test_distributed
VALUES (
    1001,
    'one_keeper_down',
    now()
);

SYSTEM FLUSH DISTRIBUTED
ha.fault_test_distributed;
"""

        one_keeper_code, one_keeper_output = (
            clickhouse_multiquery(
                MAIN_NODE,
                insert_one_keeper_sql,
                timeout=120,
                check=False,
            )
        )

        add_section(
            lines,
            "Scenario 2 — INSERT with one Keeper down",
            (
                f"Return code: {one_keeper_code}\n"
                f"{one_keeper_output or 'INSERT succeeded.'}"
            ),
        )

        add_section(
            lines,
            "Scenario 2 — synchronize replicas",
            sync_fault_replicas(),
        )

        add_section(
            lines,
            "Scenario 2 — test row distribution",
            fault_table_counts(),
        )

        _, start_keeper1 = docker(
            ["start", "group1-keeper1"],
            check=False,
        )

        time.sleep(12)

        add_section(
            lines,
            "Scenario 2 — restore keeper1",
            (
                f"{start_keeper1}\n\n"
                f"{keeper_health()}"
            ),
        )

        # ------------------------------------------------------------
        # Сценарий 3: потеря Keeper-кворума
        # ------------------------------------------------------------

        stopped_keeper_outputs: list[str] = []

        for keeper in [
            "group1-keeper1",
            "group1-keeper2",
        ]:
            _, output = docker(
                ["stop", keeper]
            )
            stopped_keeper_outputs.append(output)

        add_section(
            lines,
            "Scenario 3 — stop keeper1 and keeper2",
            "\n".join(stopped_keeper_outputs),
        )

        time.sleep(5)

        add_section(
            lines,
            "Scenario 3 — Keeper health without quorum",
            keeper_health(),
        )

        no_quorum_query_id = (
            f"fault_no_quorum_{int(time.time())}"
        )

        no_quorum_code, no_quorum_output = (
            clickhouse_query_with_id(
                MAIN_NODE,
                """
INSERT INTO ha.fault_test_local
VALUES (
    2001,
    'no_quorum',
    now()
)
""",
                query_id=no_quorum_query_id,
                timeout=25,
                check=False,
            )
        )

        add_section(
            lines,
            "Scenario 3 — INSERT without Keeper quorum",
            (
                f"Return code: {no_quorum_code}\n"
                f"{no_quorum_output}"
            ),
        )

        kill_code, kill_output = clickhouse_query(
            MAIN_NODE,
            (
                "KILL QUERY WHERE query_id = "
                f"'{no_quorum_query_id}' ASYNC"
            ),
            timeout=30,
            check=False,
        )

        add_section(
            lines,
            "Scenario 3 — cancel timed-out INSERT",
            (
                f"Return code: {kill_code}\n"
                f"{kill_output or 'Query was cancelled or already stopped.'}"
            ),
        )

        before_recovery_code, before_recovery_output = (
            clickhouse_query(
                MAIN_NODE,
                """
SELECT
    countIf(scenario = 'no_quorum')
        AS no_quorum_rows
FROM ha.fault_test_local
FORMAT TabSeparatedWithNames
""",
                timeout=30,
                check=False,
            )
        )

        add_section(
            lines,
            "Scenario 3 — verify INSERT was not committed",
            (
                f"Return code: {before_recovery_code}\n"
                f"{before_recovery_output}"
            ),
        )

        select_code, select_output = clickhouse_query(
            MAIN_NODE,
            """
SELECT
    hostName() AS node,
    count() AS local_metrics_rows
FROM ha.metrics_local
FORMAT TabSeparatedWithNames
""",
            timeout=60,
            check=False,
        )

        add_section(
            lines,
            "Scenario 3 — local SELECT without Keeper quorum",
            (
                f"Return code: {select_code}\n"
                f"{select_output}"
            ),
        )

        restored_keepers: list[str] = []

        for keeper in [
            "group1-keeper1",
            "group1-keeper2",
        ]:
            _, output = docker(
                ["start", keeper],
                check=False,
            )
            restored_keepers.append(output)

        time.sleep(8)

        add_section(
            lines,
            "Scenario 3 — restore Keeper quorum",
            (
                "\n".join(restored_keepers)
                + "\n\n"
                + keeper_health()
            ),
        )

        add_section(
            lines,
            "Scenario 3 — rows after Keeper recovery",
            fault_table_counts(),
        )

        _, final_metrics_count = clickhouse_query(
            MAIN_NODE,
            """
SELECT count() AS distributed_rows
FROM ha.metrics_distributed
FORMAT TabSeparatedWithNames
""",
        )

        add_section(
            lines,
            "Final telemetry count",
            final_metrics_count,
        )

        add_section(
            lines,
            "Remove temporary test tables",
            cleanup_fault_tables(),
        )

        lines.append("")
        lines.append("Expected conclusions:")
        lines.append(
            "- loss of shard 2 breaks Distributed queries "
            "that require both shards"
        )
        lines.append(
            "- local data on shard 1 remains readable"
        )
        lines.append(
            "- loss of one Keeper preserves quorum and INSERT works"
        )
        lines.append(
            "- loss of two Keepers removes quorum and INSERT fails"
        )
        lines.append(
            "- local SELECT continues to work without Keeper quorum"
        )
        lines.append(
            "- after recovery the telemetry count remains 5000000"
        )

    except Exception as error:
        add_section(
            lines,
            "UNEXPECTED SCRIPT ERROR",
            str(error),
        )

    finally:
        add_section(
            lines,
            "Final service recovery",
            restore_all_services(),
        )

        OUTPUT_FILE.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

        print("\n".join(lines))


if __name__ == "__main__":
    main()