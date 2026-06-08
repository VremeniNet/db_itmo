import base64
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]

OUTPUT_FILE = (
    ROOT_DIR
    / "checks"
    / "monitoring_status.txt"
)

MONITORING_SQL_FILE = (
    ROOT_DIR
    / "sql"
    / "pg"
    / "04_monitoring.sql"
)

POSTGRES_CONTAINER = "group2-postgres"
CLICKHOUSE_CONTAINER = "group2-ch-s1-r1"

MANTICORE_HTTP = "http://127.0.0.1:19308"
GRAFANA_URL = "http://127.0.0.1:33005"

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = ROOT_DIR / ".env"

    if not env_file.exists():
        return values

    for raw_line in env_file.read_text(
        encoding="utf-8",
    ).splitlines():
        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def run_command(
    command: list[str],
    input_text: str | None = None,
    timeout: int = 300,
    check: bool = True,
) -> tuple[int, str]:
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

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with code "
            f"{result.returncode}:\n"
            f"{' '.join(command)}\n\n"
            f"{output}"
        )

    return result.returncode, output


def postgres_query(
    sql: str,
    timeout: int = 120,
) -> str:
    _, output = run_command(
        [
            "docker",
            "exec",
            "-i",
            POSTGRES_CONTAINER,
            "psql",
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "ecommerce",
            "-c",
            sql,
        ],
        timeout=timeout,
    )

    return output.strip()


def postgres_execute_file(path: Path) -> str:
    sql = path.read_text(encoding="utf-8")

    _, output = run_command(
        [
            "docker",
            "exec",
            "-i",
            POSTGRES_CONTAINER,
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "ecommerce",
        ],
        input_text=sql,
        timeout=300,
    )

    return output


def clickhouse_query(
    sql: str,
    timeout: int = 120,
) -> str:
    _, output = run_command(
        [
            "docker",
            "exec",
            "-i",
            CLICKHOUSE_CONTAINER,
            "clickhouse-client",
            "--query",
            sql,
        ],
        timeout=timeout,
    )

    return output.strip()


def clickhouse_multiquery(
    sql: str,
    timeout: int = 120,
) -> str:
    _, output = run_command(
        [
            "docker",
            "exec",
            "-i",
            CLICKHOUSE_CONTAINER,
            "clickhouse-client",
            "--multiquery",
        ],
        input_text=sql,
        timeout=timeout,
    )

    return output.strip()


def http_request(
    url: str,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> str:
    request = urllib.request.Request(
        url,
        data=data,
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
    attempts: int = 20,
) -> Any:
    last_error = ""

    for _ in range(attempts):
        try:
            return json.loads(
                http_request(
                    url,
                    headers=headers,
                )
            )
        except Exception as error:
            last_error = str(error)
            time.sleep(2)

    raise RuntimeError(last_error)


def manticore_sql(sql: str) -> str:
    body = urllib.parse.urlencode(
        {"query": sql}
    ).encode("utf-8")

    return http_request(
        f"{MANTICORE_HTTP}/sql?mode=raw",
        data=body,
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded"
        },
        timeout=60,
    )


def parse_manticore_value(
    response: str,
    column: str,
) -> Any:
    parsed = json.loads(response)

    if isinstance(parsed, list):
        if not parsed:
            raise RuntimeError(
                "Manticore returned an empty list"
            )

        result_set = parsed[0]
    else:
        result_set = parsed

    rows = result_set.get("data", [])

    if not rows:
        raise RuntimeError(
            f"Manticore returned no rows: {response}"
        )

    return rows[0][column]


def measure_postgres_tps() -> float:
    counter_sql = """
SELECT
    xact_commit + xact_rollback
FROM pg_stat_database
WHERE datname = current_database();
"""

    before = int(
        postgres_query(counter_sql)
    )

    test_queries = "; ".join(
        "SELECT 1"
        for _ in range(20)
    )

    started_at = time.perf_counter()

    postgres_query(test_queries)

    elapsed = time.perf_counter() - started_at

    after = int(
        postgres_query(counter_sql)
    )

    if elapsed <= 0:
        return 0.0

    return (after - before) / elapsed


def clickhouse_query_counter() -> int:
    output = clickhouse_query(
        """
SELECT
    sum(value)
FROM clusterAllReplicas(
    'cluster_2x2',
    system.events
)
WHERE event = 'Query'
FORMAT TabSeparatedRaw
"""
    )

    return int(output)


def measure_clickhouse_qps() -> float:
    before = clickhouse_query_counter()

    test_queries = ";\n".join(
        "SELECT 1"
        for _ in range(20)
    )

    started_at = time.perf_counter()

    clickhouse_multiquery(
        test_queries + ";"
    )

    elapsed = time.perf_counter() - started_at

    after = clickhouse_query_counter()

    if elapsed <= 0:
        return 0.0

    return (after - before) / elapsed


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
        (
            f"{grafana_user}:"
            f"{grafana_password}"
        ).encode("utf-8")
    ).decode("ascii")

    grafana_headers = {
        "Authorization": (
            f"Basic {credentials}"
        )
    }

    lines: list[str] = []

    lines.append(
        "Multi-DB Grafana monitoring verification"
    )

    schema_result = postgres_execute_file(
        MONITORING_SQL_FILE
    )

    add_section(
        lines,
        "Create PostgreSQL monitoring table",
        schema_result
        or "Monitoring table is ready.",
    )

    pg_active_connections = int(
        postgres_query(
            """
SELECT count(*)
FROM pg_stat_activity
WHERE datname = current_database();
"""
        )
    )

    pg_tps = measure_postgres_tps()

    pg_database_size_bytes = int(
        postgres_query(
            """
SELECT pg_database_size(
    current_database()
);
"""
        )
    )

    ch_rows = int(
        clickhouse_query(
            """
SELECT count()
FROM ecommerce.orders_analytics_distributed
FORMAT TabSeparatedRaw
"""
        )
    )

    orders_processed = int(
        clickhouse_query(
            """
SELECT uniqExact(order_id)
FROM ecommerce.orders_analytics_distributed
FORMAT TabSeparatedRaw
"""
        )
    )

    ch_qps = measure_clickhouse_qps()

    ch_min_active_replicas = int(
        clickhouse_query(
            """
SELECT min(active_replicas)
FROM clusterAllReplicas(
    'cluster_2x2',
    system.replicas
)
WHERE database = 'ecommerce'
FORMAT TabSeparatedRaw
"""
        )
    )

    ch_replication_queue = int(
        clickhouse_query(
            """
SELECT sum(queue_size)
FROM clusterAllReplicas(
    'cluster_2x2',
    system.replicas
)
WHERE database = 'ecommerce'
FORMAT TabSeparatedRaw
"""
        )
    )

    manticore_count_response = manticore_sql(
        """
SELECT
    COUNT(*) AS documents_count
FROM reviews
"""
    )

    manticore_documents = int(
        parse_manticore_value(
            manticore_count_response,
            "documents_count",
        )
    )

    search_started_at = time.perf_counter()

    manticore_search_response = manticore_sql(
        """
SELECT
    id,
    title,
    rating,
    WEIGHT() AS weight
FROM reviews
WHERE MATCH('качество сборки')
ORDER BY weight DESC
LIMIT 10
"""
    )

    manticore_search_ms = (
        time.perf_counter()
        - search_started_at
    ) * 1000

    reviews_processed = manticore_documents

    insert_sql = f"""
INSERT INTO monitoring.pipeline_metrics (
    pg_active_connections,
    pg_tps,
    pg_database_size_bytes,
    ch_rows,
    ch_qps,
    ch_min_active_replicas,
    ch_replication_queue,
    manticore_documents,
    manticore_search_ms,
    orders_processed,
    reviews_processed,
    last_sync
)
VALUES (
    {pg_active_connections},
    {pg_tps:.3f},
    {pg_database_size_bytes},
    {ch_rows},
    {ch_qps:.3f},
    {ch_min_active_replicas},
    {ch_replication_queue},
    {manticore_documents},
    {manticore_search_ms:.3f},
    {orders_processed},
    {reviews_processed},
    now()
)
RETURNING
    metric_id,
    collected_at;
"""

    inserted_snapshot = postgres_query(
        insert_sql
    )

    metrics_summary = f"""
PostgreSQL active connections: {pg_active_connections}
PostgreSQL TPS: {pg_tps:.3f}
PostgreSQL database size: {pg_database_size_bytes} bytes

ClickHouse rows: {ch_rows}
ClickHouse unique orders: {orders_processed}
ClickHouse QPS: {ch_qps:.3f}
ClickHouse minimum active replicas: {ch_min_active_replicas}
ClickHouse replication queue: {ch_replication_queue}

ManticoreSearch documents: {manticore_documents}
ManticoreSearch search time: {manticore_search_ms:.3f} ms
"""

    add_section(
        lines,
        "Collected database metrics",
        metrics_summary.strip(),
    )

    add_section(
        lines,
        "Inserted monitoring snapshot",
        inserted_snapshot,
    )

    add_section(
        lines,
        "ManticoreSearch test response",
        manticore_search_response,
    )

    grafana_health = request_json(
        f"{GRAFANA_URL}/api/health"
    )

    add_section(
        lines,
        "Grafana health",
        json.dumps(
            grafana_health,
            ensure_ascii=False,
            indent=2,
        ),
    )

    postgres_datasource = request_json(
        (
            f"{GRAFANA_URL}"
            "/api/datasources/uid/postgresql"
        ),
        headers=grafana_headers,
    )

    clickhouse_datasource = request_json(
        (
            f"{GRAFANA_URL}"
            "/api/datasources/uid/clickhouse"
        ),
        headers=grafana_headers,
    )

    add_section(
        lines,
        "Provisioned PostgreSQL datasource",
        json.dumps(
            postgres_datasource,
            ensure_ascii=False,
            indent=2,
        ),
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

    dashboard_search = request_json(
        (
            f"{GRAFANA_URL}"
            "/api/search?"
            + urllib.parse.urlencode(
                {
                    "query":
                        "Multi-DB Pipeline"
                }
            )
        ),
        headers=grafana_headers,
    )

    add_section(
        lines,
        "Provisioned Grafana dashboard",
        json.dumps(
            dashboard_search,
            ensure_ascii=False,
            indent=2,
        ),
    )

    dashboard = request_json(
        (
            f"{GRAFANA_URL}"
            "/api/dashboards/uid/"
            "multi-db-pipeline"
        ),
        headers=grafana_headers,
    )

    panels = dashboard[
        "dashboard"
    ].get("panels", [])

    panel_lines: list[str] = []

    for panel in panels:
        datasource = panel.get(
            "datasource",
            {},
        )

        panel_lines.append(
            f"id={panel.get('id')}, "
            f"title={panel.get('title')}, "
            f"type={panel.get('type')}, "
            f"datasource="
            f"{datasource.get('uid', '')}"
        )

        for target in panel.get(
            "targets",
            [],
        ):
            raw_sql = target.get(
                "rawSql",
                "",
            ).strip()

            if raw_sql:
                panel_lines.append(
                    "  SQL: "
                    + " ".join(
                        raw_sql.split()
                    )
                )

    add_section(
        lines,
        "Grafana dashboard panels",
        "\n".join(panel_lines),
    )

    snapshot_result = postgres_query(
        """
SELECT
    collected_at,
    pg_active_connections,
    pg_tps,
    pg_size_pretty(
        pg_database_size_bytes
    ) AS pg_database_size,
    ch_rows,
    ch_qps,
    ch_min_active_replicas,
    ch_replication_queue,
    manticore_documents,
    manticore_search_ms,
    orders_processed,
    reviews_processed,
    last_sync
FROM monitoring.pipeline_metrics
ORDER BY collected_at DESC
LIMIT 1;
"""
    )

    add_section(
        lines,
        "Latest pipeline monitoring snapshot",
        snapshot_result,
    )

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))


if __name__ == "__main__":
    main()