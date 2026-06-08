import subprocess
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

POSTGRES_CONTAINER = "group2-postgres"
CLICKHOUSE_MAIN = "group2-ch-s1-r1"

CLICKHOUSE_NODES = [
    "group2-ch-s1-r1",
    "group2-ch-s1-r2",
    "group2-ch-s2-r1",
    "group2-ch-s2-r2",
]

ETL_OUTPUT_FILE = ROOT_DIR / "checks" / "etl_sync.txt"
ANALYTICS_OUTPUT_FILE = (
    ROOT_DIR / "checks" / "ch_analytics.txt"
)
TEMP_CSV_FILE = (
    ROOT_DIR / "checks" / "_orders_analytics.csv"
)


COPY_SQL = """
COPY (
    SELECT
        o.order_date::date AS order_date,
        o.order_id,
        c.full_name AS customer_name,
        c.region,
        p.name AS product_name,
        cat.name AS category,
        oi.quantity,
        oi.unit_price AS price,
        round(
            oi.quantity * oi.unit_price,
            2
        ) AS line_total,
        o.status AS order_status
    FROM orders AS o
    JOIN customers AS c
        ON c.customer_id = o.customer_id
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    JOIN products AS p
        ON p.product_id = oi.product_id
    JOIN categories AS cat
        ON cat.category_id = p.category_id
) TO STDOUT WITH (
    FORMAT CSV
)
"""


def run_command(
    command: list[str],
    input_text: str | None = None,
    timeout: int = 1800,
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
            f"Command failed with code {result.returncode}:\n"
            f"{' '.join(command)}\n\n"
            f"{output}"
        )

    return result.returncode, output


def clickhouse_multiquery(
    sql: str,
    timeout: int = 600,
) -> str:
    _, output = run_command(
        [
            "docker",
            "exec",
            "-i",
            CLICKHOUSE_MAIN,
            "clickhouse-client",
            "--multiquery",
        ],
        input_text=sql,
        timeout=timeout,
    )

    return output


def clickhouse_query(
    container: str,
    sql: str,
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
            "--query",
            sql,
        ],
        timeout=timeout,
        check=check,
    )


def postgres_query(sql: str) -> str:
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
        timeout=300,
    )

    return output


def export_postgres_csv() -> float:
    started_at = time.perf_counter()

    command = [
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
        COPY_SQL,
    ]

    with TEMP_CSV_FILE.open("wb") as output_file:
        result = subprocess.run(
            command,
            cwd=ROOT_DIR,
            stdout=output_file,
            stderr=subprocess.PIPE,
            timeout=1800,
        )

    if result.returncode != 0:
        error = result.stderr.decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"PostgreSQL export failed:\n{error}"
        )

    return time.perf_counter() - started_at


def import_clickhouse_csv() -> float:
    started_at = time.perf_counter()

    command = [
        "docker",
        "exec",
        "-i",
        CLICKHOUSE_MAIN,
        "clickhouse-client",
        "--insert_distributed_sync=1",
        "--query",
        (
            "INSERT INTO "
            "ecommerce.orders_analytics_distributed "
            "FORMAT CSV"
        ),
    ]

    with TEMP_CSV_FILE.open("rb") as input_file:
        result = subprocess.run(
            command,
            cwd=ROOT_DIR,
            stdin=input_file,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=1800,
        )

    output = result.stdout.decode(
        "utf-8",
        errors="replace",
    ).strip()

    if result.returncode != 0:
        raise RuntimeError(
            f"ClickHouse import failed:\n{output}"
        )

    return time.perf_counter() - started_at


def sync_replicas() -> str:
    lines: list[str] = []

    tables = [
        "orders_analytics_local",
        "category_revenue_local",
        "daily_orders_local",
    ]

    for container in CLICKHOUSE_NODES:
        for table in tables:
            code, output = clickhouse_query(
                container,
                (
                    "SYSTEM SYNC REPLICA "
                    f"ecommerce.{table}"
                ),
                timeout=300,
                check=False,
            )

            lines.append(
                f"{container} / {table}: "
                f"code={code}, "
                f"result={output or 'synchronized'}"
            )

    return "\n".join(lines)


def local_counts() -> str:
    query = """
SELECT
    hostName() AS node,
    count() AS rows,
    uniqExact(order_id) AS unique_orders,
    round(sum(toFloat64(line_total)), 2)
        AS revenue
FROM ecommerce.orders_analytics_local
FORMAT TabSeparatedWithNames
"""

    lines: list[str] = []

    for container in CLICKHOUSE_NODES:
        code, output = clickhouse_query(
            container,
            query,
            check=False,
        )

        lines.append(f"[{container}] code={code}")
        lines.append(output)
        lines.append("")

    return "\n".join(lines)


def replica_status() -> str:
    query = """
SELECT
    hostName() AS node,
    table,
    replica_name,
    total_replicas,
    active_replicas,
    queue_size,
    absolute_delay
FROM system.replicas
WHERE database = 'ecommerce'
ORDER BY table
FORMAT TabSeparatedWithNames
"""

    lines: list[str] = []

    for container in CLICKHOUSE_NODES:
        code, output = clickhouse_query(
            container,
            query,
            check=False,
        )

        lines.append(f"[{container}] code={code}")
        lines.append(output)
        lines.append("")

    return "\n".join(lines)


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
    ETL_OUTPUT_FILE.parent.mkdir(exist_ok=True)

    tables_sql = (
        ROOT_DIR
        / "sql"
        / "ch"
        / "01_tables.sql"
    ).read_text(encoding="utf-8")

    mv_sql = (
        ROOT_DIR
        / "sql"
        / "ch"
        / "02_mv.sql"
    ).read_text(encoding="utf-8")

    analytics_sql = (
        ROOT_DIR
        / "sql"
        / "ch"
        / "03_analytics.sql"
    ).read_text(encoding="utf-8")

    etl_lines: list[str] = []
    etl_lines.append(
        "PostgreSQL to ClickHouse ETL"
    )

    add_section(
        etl_lines,
        "Create ClickHouse analytics tables",
        clickhouse_multiquery(
            tables_sql + "\n" + mv_sql,
            timeout=600,
        )
        or "Tables and materialized views created.",
    )

    truncate_sql = """
TRUNCATE TABLE ecommerce.category_revenue_local
ON CLUSTER cluster_2x2
SYNC;

TRUNCATE TABLE ecommerce.daily_orders_local
ON CLUSTER cluster_2x2
SYNC;

TRUNCATE TABLE ecommerce.orders_analytics_local
ON CLUSTER cluster_2x2
SYNC;
"""

    add_section(
        etl_lines,
        "Clean previous ClickHouse data",
        clickhouse_multiquery(
            truncate_sql,
            timeout=600,
        )
        or "Analytics tables truncated.",
    )

    pg_source_count = postgres_query(
        "SELECT count(*) FROM order_items;"
    )

    add_section(
        etl_lines,
        "PostgreSQL source row count",
        pg_source_count,
    )

    export_elapsed = export_postgres_csv()

    csv_size_mb = (
        TEMP_CSV_FILE.stat().st_size
        / 1024
        / 1024
    )

    add_section(
        etl_lines,
        "Export PostgreSQL JOIN to CSV",
        (
            f"Export time: {export_elapsed:.3f} sec\n"
            f"CSV size: {csv_size_mb:.2f} MB"
        ),
    )

    import_elapsed = import_clickhouse_csv()

    add_section(
        etl_lines,
        "Import CSV into ClickHouse",
        f"Import time: {import_elapsed:.3f} sec",
    )

    clickhouse_multiquery(
        """
SYSTEM FLUSH DISTRIBUTED
ecommerce.orders_analytics_distributed;
""",
        timeout=300,
    )

    add_section(
        etl_lines,
        "Synchronize ClickHouse replicas",
        sync_replicas(),
    )

    _, distributed_count = clickhouse_query(
        CLICKHOUSE_MAIN,
        """
SELECT
    count() AS analytics_rows,
    uniqExact(order_id) AS unique_orders
FROM ecommerce.orders_analytics_distributed
FORMAT TabSeparatedWithNames
""",
    )

    add_section(
        etl_lines,
        "ClickHouse distributed count",
        distributed_count,
    )

    add_section(
        etl_lines,
        "Local data distribution",
        local_counts(),
    )

    add_section(
        etl_lines,
        "Replication status",
        replica_status(),
    )

    etl_lines.append(
        "Expected source rows: 1000002"
    )

    ETL_OUTPUT_FILE.write_text(
        "\n".join(etl_lines),
        encoding="utf-8",
    )

    analytics_output = clickhouse_multiquery(
        analytics_sql,
        timeout=600,
    )

    ANALYTICS_OUTPUT_FILE.write_text(
        "ClickHouse analytics queries\n\n"
        + analytics_output,
        encoding="utf-8",
    )

    try:
        TEMP_CSV_FILE.unlink()
    except FileNotFoundError:
        pass

    print("\n".join(etl_lines))
    print("")
    print(analytics_output)


if __name__ == "__main__":
    main()