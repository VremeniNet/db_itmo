import socket
import subprocess
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
EXPERIMENT_B_FILE = CHECKS_DIR / "experiment_b.txt"

KEEPERS = [
    ("keeper1", "127.0.0.1", 9181),
    ("keeper2", "127.0.0.1", 9182),
    ("keeper3", "127.0.0.1", 9183),
]


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


def ch_query(container: str, query: str, timeout: int = 60) -> str:
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
    )


def send_4lw_command(host: str, port: int, command: str) -> str:
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.sendall((command + "\n").encode("utf-8"))

        chunks = []
        sock.settimeout(3)

        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                break

            if not data:
                break

            chunks.append(data)

    return b"".join(chunks).decode("utf-8", errors="replace").strip()


def keeper_check() -> str:
    lines = []

    for name, host, port in KEEPERS:
        lines.append(f"[{name} {host}:{port}]")

        try:
            ruok = send_4lw_command(host, port, "ruok")
        except Exception as error:
            ruok = f"ERROR: {error}"

        lines.append(f"ruok: {ruok}")

        try:
            mntr = send_4lw_command(host, port, "mntr")
            state_lines = [
                line for line in mntr.splitlines()
                if "zk_server_state" in line or "zk_synced_followers" in line
            ]
            lines.extend(state_lines if state_lines else ["mntr: no state lines"])
        except Exception as error:
            lines.append(f"mntr ERROR: {error}")

        lines.append("")

    return "\n".join(lines)


def append_section(lines: list[str], title: str, content: str) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)
    lines.append(content)
    lines.append("")


def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    lines = []
    lines.append("Experiment B — Keeper quorum failure")
    lines.append("")

    append_section(lines, "Start all Keeper nodes", "\n".join([
        docker(["start", "idz3-keeper1"]),
        docker(["start", "idz3-keeper2"]),
        docker(["start", "idz3-keeper3"]),
    ]))

    time.sleep(5)

    append_section(lines, "Initial Keeper health", keeper_check())

    append_section(lines, "Initial row count", ch_query(
        "idz3-ch1",
        """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_b_one_keeper_down') AS one_keeper_down_rows,
    countIf(event_type = 'experiment_b_no_quorum') AS no_quorum_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
"""
    ))

    append_section(lines, "Stop keeper1", docker(["stop", "idz3-keeper1"]))

    time.sleep(5)

    append_section(lines, "Keeper health after stopping keeper1", keeper_check())

    insert_with_quorum_query = """
INSERT INTO idz3.events
SELECT
    now() + toIntervalSecond(number) AS event_time,
    'experiment_b_one_keeper_down' AS event_type,
    toUInt64(2000000 + number) AS user_id,
    concat('experiment_b_one_keeper_down_payload_', toString(number)) AS payload
FROM numbers(1000)
"""
    append_section(lines, "Insert with one Keeper down", ch_query("idz3-ch1", insert_with_quorum_query, timeout=60))

    append_section(lines, "Counts after insert with one Keeper down", "\n".join([
        "[idz3-ch1]",
        ch_query(
            "idz3-ch1",
            """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_b_one_keeper_down') AS one_keeper_down_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
"""
        ),
        "",
        "[idz3-ch2]",
        ch_query(
            "idz3-ch2",
            """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_b_one_keeper_down') AS one_keeper_down_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
"""
        ),
        "",
        "[idz3-ch3]",
        ch_query(
            "idz3-ch3",
            """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_b_one_keeper_down') AS one_keeper_down_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
"""
        ),
    ]))

    append_section(lines, "Stop keeper2, quorum is lost", docker(["stop", "idz3-keeper2"]))

    time.sleep(5)

    append_section(lines, "Keeper health after stopping keeper1 and keeper2", keeper_check())

    insert_without_quorum_query = """
INSERT INTO idz3.events
SELECT
    now() + toIntervalSecond(number) AS event_time,
    'experiment_b_no_quorum' AS event_type,
    toUInt64(3000000 + number) AS user_id,
    concat('experiment_b_no_quorum_payload_', toString(number)) AS payload
FROM numbers(1000)
"""
    append_section(lines, "Insert without Keeper quorum, expected error", ch_query("idz3-ch1", insert_without_quorum_query, timeout=40))

    append_section(lines, "SELECT still works without Keeper quorum", ch_query(
        "idz3-ch1",
        """
SELECT
    hostName() AS node,
    count() AS total_rows,
    countIf(event_type = 'experiment_b_one_keeper_down') AS one_keeper_down_rows,
    countIf(event_type = 'experiment_b_no_quorum') AS no_quorum_rows
FROM idz3.events
FORMAT TabSeparatedWithNames
"""
    ))

    append_section(lines, "Start keeper1 and keeper2 again", "\n".join([
        docker(["start", "idz3-keeper1"]),
        docker(["start", "idz3-keeper2"]),
    ]))

    time.sleep(8)

    append_section(lines, "Keeper health after recovery", keeper_check())

    append_section(lines, "Final system.replicas from ch1", ch_query(
        "idz3-ch1",
        """
SELECT
    database,
    table,
    replica_name,
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
    ))

    EXPERIMENT_B_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()