import json
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT_DIR / "checks" / "infrastructure.txt"

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)

EXPECTED_SERVICES = {
    "postgres",
    "keeper1",
    "keeper2",
    "keeper3",
    "ch-s1-r1",
    "ch-s1-r2",
    "ch-s2-r1",
    "ch-s2-r2",
    "manticore",
    "grafana",
}

CLICKHOUSE_NODES = [
    "group2-ch-s1-r1",
    "group2-ch-s1-r2",
    "group2-ch-s2-r1",
    "group2-ch-s2-r2",
]


def run(
    command: list[str],
    timeout: int = 120,
) -> tuple[int, str]:
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

    return result.returncode, result.stdout.strip()


def http_get(url: str) -> str:
    request = urllib.request.Request(url)

    with NO_PROXY_OPENER.open(
        request,
        timeout=10,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        ).strip()


def manticore_sql(query: str) -> str:
    body = urllib.parse.urlencode(
        {"query": query}
    ).encode("utf-8")

    request = urllib.request.Request(
        "http://127.0.0.1:19308/sql?mode=raw",
        data=body,
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    with NO_PROXY_OPENER.open(
        request,
        timeout=20,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        ).strip()


def keeper_ruok(port: int) -> str:
    with socket.create_connection(
        ("127.0.0.1", port),
        timeout=5,
    ) as connection:
        connection.sendall(b"ruok\n")
        connection.settimeout(5)
        return connection.recv(1024).decode(
            "utf-8",
            errors="replace",
        ).strip()


def main() -> None:
    lines: list[str] = []
    failed = False

    lines.append("Multi-DB infrastructure check")
    lines.append("")

    code, services_output = run(
        [
            "docker",
            "compose",
            "ps",
            "--services",
            "--status",
            "running",
        ]
    )

    running_services = {
        line.strip()
        for line in services_output.splitlines()
        if line.strip()
    }

    missing = EXPECTED_SERVICES - running_services

    lines.append("Running services:")
    lines.extend(sorted(running_services))
    lines.append("")

    if code == 0 and not missing:
        lines.append("All 10 services are running.")
    else:
        failed = True
        lines.append(f"Missing services: {sorted(missing)}")

    lines.append("")
    lines.append("PostgreSQL:")

    pg_code, pg_output = run(
        [
            "docker",
            "exec",
            "-i",
            "group2-postgres",
            "psql",
            "-U",
            "postgres",
            "-d",
            "ecommerce",
            "-tAc",
            "SELECT version();",
        ]
    )

    lines.append(f"Return code: {pg_code}")
    lines.append(pg_output)

    if pg_code != 0:
        failed = True

    lines.append("")
    lines.append("ClickHouse nodes:")

    for container in CLICKHOUSE_NODES:
        ch_code, ch_output = run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "clickhouse-client",
                "--query",
                (
                    "SELECT hostName(), version() "
                    "FORMAT TabSeparated"
                ),
            ]
        )

        lines.append(
            f"{container}: code={ch_code}, "
            f"result={ch_output}"
        )

        if ch_code != 0:
            failed = True

    cluster_code, cluster_output = run(
        [
            "docker",
            "exec",
            "-i",
            "group2-ch-s1-r1",
            "clickhouse-client",
            "--query",
            """
SELECT
    cluster,
    shard_num,
    replica_num,
    host_name
FROM system.clusters
WHERE cluster = 'cluster_2x2'
ORDER BY shard_num, replica_num
FORMAT TabSeparatedWithNames
""",
        ]
    )

    lines.append("")
    lines.append("ClickHouse cluster:")
    lines.append(cluster_output)

    if cluster_code != 0:
        failed = True

    lines.append("")
    lines.append("Keeper health:")

    for port in [29581, 29582, 29583]:
        try:
            lines.append(
                f"127.0.0.1:{port}: "
                f"{keeper_ruok(port)}"
            )
        except Exception as error:
            failed = True
            lines.append(
                f"127.0.0.1:{port}: ERROR: {error}"
            )

    lines.append("")
    lines.append("ManticoreSearch:")

    try:
        manticore_output = manticore_sql(
            "SHOW TABLES"
        )
        lines.append(manticore_output)
    except Exception as error:
        failed = True
        lines.append(f"ERROR: {error}")

    lines.append("")
    lines.append("Grafana:")

    try:
        grafana_health = http_get(
            "http://127.0.0.1:33005/api/health"
        )
        lines.append(
            json.dumps(
                json.loads(grafana_health),
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as error:
        failed = True
        lines.append(f"ERROR: {error}")

    compose_code, compose_output = run(
        ["docker", "compose", "ps"]
    )

    lines.append("")
    lines.append("docker compose ps:")
    lines.append(compose_output)

    if compose_code != 0:
        failed = True

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()