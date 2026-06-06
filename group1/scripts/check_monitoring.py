import base64
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT_DIR / "checks" / "monitoring_status.txt"

PROMETHEUS_URL = "http://127.0.0.1:9095"
GRAFANA_URL = "http://127.0.0.1:3005"
NGINX_URL = "http://127.0.0.1:8085"

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)

PROMETHEUS_QUERIES = {
    "ClickHouse targets": 'up{job="clickhouse"}',
    "Healthy ClickHouse node count": 'sum(up{job="clickhouse"})',
    "MergeTree rows": (
        'ClickHouseAsyncMetrics_TotalRowsOfMergeTreeTables'
        '{job="clickhouse"}'
    ),
    "Queries per second": (
        'rate(ClickHouseProfileEvents_Query'
        '{job="clickhouse"}[1m])'
    ),
    "Replication queue": (
        'ClickHouseAsyncMetrics_ReplicasMaxQueueSize'
        '{job="clickhouse"}'
    ),
    "Replication delay": (
        'ClickHouseAsyncMetrics_ReplicasMaxAbsoluteDelay'
        '{job="clickhouse"}'
    ),
    "Memory tracking": (
        'ClickHouseMetrics_MemoryTracking'
        '{job="clickhouse"}'
    ),
}


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = ROOT_DIR / ".env"

    if not env_file.exists():
        return values

    for raw_line in env_file.read_text(
        encoding="utf-8",
    ).splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def request_text(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> str:
    request = urllib.request.Request(
        url,
        headers=headers or {},
    )

    with NO_PROXY_OPENER.open(
        request,
        timeout=timeout,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        ).strip()


def request_json(
    url: str,
    headers: dict[str, str] | None = None,
) -> Any:
    return json.loads(request_text(url, headers=headers))


def prometheus_query(expression: str) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(
        {"query": expression}
    )

    result = request_json(
        f"{PROMETHEUS_URL}/api/v1/query?{encoded}"
    )

    if result.get("status") != "success":
        raise RuntimeError(json.dumps(result, ensure_ascii=False))

    return result["data"]


def create_query_traffic(requests_count: int = 80) -> None:
    query = urllib.parse.quote(
        "SELECT 1 FORMAT TabSeparated",
        safe="",
    )

    for _ in range(requests_count):
        request_text(
            f"{NGINX_URL}/?query={query}",
            headers={"Connection": "close"},
            timeout=10,
        )


def format_prometheus_result(data: dict[str, Any]) -> str:
    result = data.get("result", [])

    if not result:
        return "No time series returned."

    lines: list[str] = []

    for series in result:
        metric = series.get("metric", {})
        value = series.get("value", [])

        instance = metric.get("instance", "")
        job = metric.get("job", "")
        hostname = metric.get("hostname", "")

        labels = {
            key: value
            for key, value in {
                "instance": instance,
                "hostname": hostname,
                "job": job,
            }.items()
            if value
        }

        lines.append(
            f"labels={labels}, value={value[-1] if value else ''}"
        )

    return "\n".join(lines)


def run_clickhouse_query(
    container: str,
    query: str,
) -> str:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "clickhouse-client",
            "--query",
            query,
        ],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip())

    return result.stdout.strip()


def add_section(
    lines: list[str],
    title: str,
    content: str,
) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)
    lines.append(content)
    lines.append("")


def main() -> None:
    env = load_env()

    grafana_user = env.get(
        "GRAFANA_ADMIN_USER",
        "admin",
    )
    grafana_password = env.get(
        "GRAFANA_ADMIN_PASSWORD",
        "admin",
    )

    credentials = base64.b64encode(
        f"{grafana_user}:{grafana_password}".encode("utf-8")
    ).decode("ascii")

    grafana_headers = {
        "Authorization": f"Basic {credentials}"
    }

    lines: list[str] = []
    lines.append("Prometheus and Grafana monitoring check")

    create_query_traffic(80)

    time.sleep(12)

    targets = request_json(
        f"{PROMETHEUS_URL}/api/v1/targets"
    )

    active_targets = targets["data"]["activeTargets"]

    target_lines: list[str] = []

    for target in active_targets:
        labels = target.get("labels", {})

        if labels.get("job") != "clickhouse":
            continue

        target_lines.append(
            "instance={instance}, health={health}, "
            "lastError={error}".format(
                instance=labels.get("instance", ""),
                health=target.get("health", ""),
                error=target.get("lastError", ""),
            )
        )

    add_section(
        lines,
        "Prometheus ClickHouse targets",
        "\n".join(target_lines),
    )

    for title, expression in PROMETHEUS_QUERIES.items():
        data = prometheus_query(expression)

        add_section(
            lines,
            title,
            f"PromQL: {expression}\n\n"
            f"{format_prometheus_result(data)}",
        )

    parts_query = """
SELECT
    hostName() AS node,
    database,
    table,
    sum(rows) AS rows,
    count() AS active_parts
FROM system.parts
WHERE active
  AND database = 'ha'
GROUP BY
    node,
    database,
    table
ORDER BY
    node,
    database,
    table
FORMAT TabSeparatedWithNames
"""

    parts_output: list[str] = []

    for container in [
        "group1-ch-s1-r1",
        "group1-ch-s1-r2",
        "group1-ch-s2-r1",
        "group1-ch-s2-r2",
    ]:
        parts_output.append(f"[{container}]")
        parts_output.append(
            run_clickhouse_query(container, parts_query)
        )
        parts_output.append("")

    add_section(
        lines,
        "system.parts row count verification",
        "\n".join(parts_output),
    )

    replicas_query = """
SELECT
    hostName() AS node,
    replica_name,
    total_replicas,
    active_replicas,
    queue_size,
    absolute_delay
FROM system.replicas
WHERE database = 'ha'
  AND table = 'metrics_local'
FORMAT TabSeparatedWithNames
"""

    replicas_output: list[str] = []

    for container in [
        "group1-ch-s1-r1",
        "group1-ch-s1-r2",
        "group1-ch-s2-r1",
        "group1-ch-s2-r2",
    ]:
        replicas_output.append(f"[{container}]")
        replicas_output.append(
            run_clickhouse_query(container, replicas_query)
        )
        replicas_output.append("")

    add_section(
        lines,
        "system.replicas verification",
        "\n".join(replicas_output),
    )

    grafana_health = request_text(
        f"{GRAFANA_URL}/api/health"
    )
    
    clickhouse_datasource = request_json(
        f"{GRAFANA_URL}/api/datasources/uid/clickhouse",
        headers=grafana_headers,
    )

    add_section(
        lines,
        "Provisioned ClickHouse datasource",
        json.dumps(
            clickhouse_datasource,
            ensure_ascii=False,
            indent=2,
        ),
    )

    clickhouse_datasource_health = request_text(
        (
            f"{GRAFANA_URL}"
            "/api/datasources/uid/clickhouse/health"
        ),
        headers=grafana_headers,
    )

    add_section(
        lines,
        "ClickHouse datasource health",
        clickhouse_datasource_health,
    )

    add_section(
        lines,
        "Grafana health",
        grafana_health,
    )

    search_query = urllib.parse.urlencode(
        {"query": "ClickHouse HA Cluster"}
    )

    dashboards = request_json(
        f"{GRAFANA_URL}/api/search?{search_query}",
        headers=grafana_headers,
    )

    add_section(
        lines,
        "Provisioned Grafana dashboard",
        json.dumps(
            dashboards,
            ensure_ascii=False,
            indent=2,
        ),
    )

    dashboard = request_json(
        f"{GRAFANA_URL}/api/dashboards/uid/clickhouse-ha",
        headers=grafana_headers,
    )

    panels = dashboard["dashboard"].get("panels", [])

    panel_lines: list[str] = []

    for panel in panels:
        datasource = panel.get("datasource", {})

        panel_lines.append(
            f"id={panel.get('id')}, "
            f"title={panel.get('title')}, "
            f"type={panel.get('type')}, "
            f"datasource={datasource.get('uid', '')}"
        )

        for target in panel.get("targets", []):
            raw_sql = target.get("rawSql", "").strip()

            if raw_sql:
                panel_lines.append(
                    "  SQL: "
                    + " ".join(raw_sql.split())
                )  

            expression = target.get("expr", "").strip()

            if expression:
                panel_lines.append(
                    f"  PromQL: {expression}"
                )

    add_section(
        lines,
        "Grafana dashboard panels",
        "\n".join(panel_lines),
    )

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))


if __name__ == "__main__":
    main()