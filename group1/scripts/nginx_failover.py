import subprocess
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT_DIR / "checks" / "nginx_failover.txt"

NGINX_URL = "http://127.0.0.1:8085"
FAILED_NODE = "group1-ch-s1-r2"

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)


def run_command(
    command: list[str],
    timeout: int = 120,
) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
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


def nginx_query(query: str, timeout: int = 30) -> str:
    encoded_query = urllib.parse.quote(query, safe="")
    url = f"{NGINX_URL}/?query={encoded_query}"

    request = urllib.request.Request(
        url,
        headers={
            "Connection": "close",
            "User-Agent": "group1-nginx-failover-test",
        },
    )

    with NO_PROXY_OPENER.open(request, timeout=timeout) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        ).strip()


def wait_for_clickhouse(
    container: str,
    timeout_seconds: int = 90,
) -> str:
    started_at = time.time()
    last_output = ""

    while time.time() - started_at < timeout_seconds:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "clickhouse-client",
                "--query",
                "SELECT 1 FORMAT TabSeparatedRaw",
            ],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        last_output = result.stdout.strip()

        if result.returncode == 0 and last_output == "1":
            return f"{container} is ready"

        time.sleep(2)

    raise RuntimeError(
        f"{container} did not become ready. "
        f"Last output: {last_output}"
    )


def collect_round_robin(
    requests_count: int,
) -> tuple[list[str], Counter[str]]:
    responses: list[str] = []
    nodes: Counter[str] = Counter()

    for request_number in range(1, requests_count + 1):
        try:
            node = nginx_query(
                "SELECT hostName() FORMAT TabSeparated"
            )

            responses.append(
                f"Request {request_number:02d}: {node}"
            )
            nodes[node] += 1

        except Exception as error:
            responses.append(
                f"Request {request_number:02d}: ERROR: {error}"
            )
            nodes["ERROR"] += 1

        time.sleep(0.15)

    return responses, nodes


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


def format_counts(counts: Counter[str]) -> str:
    if not counts:
        return "No responses"

    return "\n".join(
        f"{node}: {count}"
        for node, count in sorted(counts.items())
    )


def nginx_logs() -> str:
    return run_command(
        [
            "docker",
            "logs",
            "--tail",
            "50",
            "group1-nginx",
        ],
        timeout=30,
    )


def main() -> None:
    lines: list[str] = []

    lines.append("Nginx round-robin and ClickHouse failover test")
    lines.append("")
    lines.append(f"Stopped node during test: {FAILED_NODE}")

    run_command(["docker", "start", FAILED_NODE])
    wait_for_clickhouse(FAILED_NODE)

    add_section(lines, "Initial Docker Compose status")
    lines.append(
        run_command(["docker", "compose", "ps"])
    )

    add_section(
        lines,
        "Round-robin before node failure",
    )

    before_responses, before_counts = collect_round_robin(16)

    lines.extend(before_responses)
    lines.append("")
    lines.append("Response distribution:")
    lines.append(format_counts(before_counts))

    add_section(
        lines,
        "Distributed query before node failure",
    )

    lines.append(
        nginx_query(
            """
SELECT count()
FROM ha.metrics_distributed
FORMAT TabSeparated
""".strip()
        )
    )

    add_section(
        lines,
        f"Stop ClickHouse node {FAILED_NODE}",
    )

    lines.append(
        run_command(["docker", "stop", FAILED_NODE])
    )

    time.sleep(3)

    add_section(
        lines,
        "Requests while one ClickHouse node is stopped",
    )

    failure_responses, failure_counts = collect_round_robin(20)

    lines.extend(failure_responses)
    lines.append("")
    lines.append("Response distribution:")
    lines.append(format_counts(failure_counts))

    add_section(
        lines,
        "Distributed query while one node is stopped",
    )

    try:
        distributed_count = nginx_query(
            """
SELECT count()
FROM ha.metrics_distributed
FORMAT TabSeparated
""".strip(),
            timeout=60,
        )
        lines.append(distributed_count)
    except Exception as error:
        lines.append(f"ERROR: {error}")

    add_section(
        lines,
        "Nginx JSON access log during failover",
    )

    lines.append(nginx_logs())

    add_section(
        lines,
        f"Start ClickHouse node {FAILED_NODE}",
    )

    lines.append(
        run_command(["docker", "start", FAILED_NODE])
    )

    lines.append(wait_for_clickhouse(FAILED_NODE))

    time.sleep(12)

    add_section(
        lines,
        "Round-robin after node recovery",
    )

    after_responses, after_counts = collect_round_robin(16)

    lines.extend(after_responses)
    lines.append("")
    lines.append("Response distribution:")
    lines.append(format_counts(after_counts))

    add_section(
        lines,
        "Final Docker Compose status",
    )

    lines.append(
        run_command(["docker", "compose", "ps"])
    )

    lines.append("")
    lines.append("Expected conditions:")
    lines.append("- before failure requests reach all 4 ClickHouse nodes")
    lines.append("- while ch-s1-r2 is stopped all HTTP requests still succeed")
    lines.append("- stopped ch-s1-r2 is absent from successful responses")
    lines.append("- distributed count remains 5000000")
    lines.append("- JSON access log contains upstream_addr")
    lines.append("- after recovery ch-s1-r2 returns to round-robin")

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    finally:
        subprocess.run(
            ["docker", "start", FAILED_NODE],
            cwd=ROOT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )