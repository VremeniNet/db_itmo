import json
import statistics
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = (
    ROOT_DIR
    / "checks"
    / "comparison_table.txt"
)

POSTGRES_CONTAINER = "group2-postgres"
CLICKHOUSE_CONTAINER = "group2-ch-s1-r1"

MANTICORE_HTTP = "http://127.0.0.1:19308"
MANTICORE_BATCH_SIZE = 2_000

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)


def run_command(
    command: list[str],
    input_text: str | None = None,
    timeout: int = 600,
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
    timeout: int = 600,
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

    return output


def clickhouse_query(
    sql: str,
    timeout: int = 600,
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

    return output


def http_request(
    url: str,
    data: bytes,
    content_type: str,
    timeout: int = 180,
) -> str:
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": content_type,
        },
        method="POST",
    )

    with NO_PROXY_OPENER.open(
        request,
        timeout=timeout,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        ).strip()


def manticore_sql(
    sql: str,
    timeout: int = 180,
) -> str:
    body = urllib.parse.urlencode(
        {"query": sql}
    ).encode("utf-8")

    return http_request(
        f"{MANTICORE_HTTP}/sql?mode=raw",
        body,
        "application/x-www-form-urlencoded",
        timeout=timeout,
    )


def manticore_bulk(
    documents: list[dict[str, Any]],
) -> None:
    lines: list[str] = []

    for document in documents:
        lines.append(
            json.dumps(
                {
                    "insert": {
                        "index": "benchmark_records",
                        "id": document["id"],
                        "doc": {
                            "payload": document["payload"],
                            "category": document["category"],
                            "score": document["score"],
                        },
                    }
                },
                ensure_ascii=False,
            )
        )

    body = (
        "\n".join(lines) + "\n"
    ).encode("utf-8")

    response = http_request(
        f"{MANTICORE_HTTP}/bulk",
        body,
        "application/x-ndjson",
        timeout=300,
    )

    parsed = json.loads(response)

    if parsed.get("errors"):
        raise RuntimeError(
            "Manticore bulk insert returned errors:\n"
            + response[:3000]
        )


def parse_manticore_value(
    response: str,
    column: str,
) -> Any:
    parsed = json.loads(response)

    if isinstance(parsed, list):
        if not parsed:
            raise RuntimeError(
                "Manticore returned an empty result list"
            )

        result_set = parsed[0]
    else:
        result_set = parsed

    rows = result_set.get("data", [])

    if not rows:
        raise RuntimeError(
            f"Manticore returned no rows:\n{response}"
        )

    return rows[0][column]


def measure_ms(
    operation: Callable[[], Any],
    repeats: int = 5,
    warmup: int = 1,
) -> float:
    for _ in range(warmup):
        operation()

    measurements: list[float] = []

    for _ in range(repeats):
        started_at = time.perf_counter()
        operation()
        elapsed = time.perf_counter() - started_at

        measurements.append(elapsed * 1000)

    return statistics.median(measurements)


def measure_seconds(
    operation: Callable[[], Any],
) -> float:
    started_at = time.perf_counter()
    operation()
    return time.perf_counter() - started_at


def bytes_to_mb(value: int) -> float:
    return value / 1024 / 1024


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


def prepare_postgresql() -> None:
    postgres_query(
        """
DROP TABLE IF EXISTS benchmark_records;

CREATE TABLE benchmark_records (
    id       BIGINT PRIMARY KEY,
    category INTEGER NOT NULL,
    value    NUMERIC(14, 2) NOT NULL,
    payload  TEXT NOT NULL
);
"""
    )


def prepare_clickhouse() -> None:
    clickhouse_query(
        """
DROP TABLE IF EXISTS ecommerce.benchmark_records
"""
    )

    clickhouse_query(
        """
CREATE TABLE ecommerce.benchmark_records
(
    id       UInt64,
    category UInt32,
    value    Float64,
    payload  String
)
ENGINE = MergeTree
ORDER BY id
"""
    )


def prepare_manticore() -> None:
    manticore_sql(
        "DROP TABLE IF EXISTS benchmark_records"
    )

    manticore_sql(
        """
CREATE TABLE benchmark_records (
    payload  text,
    category integer,
    score    float
)
min_word_len='2'
"""
    )


def cleanup_benchmarks() -> None:
    postgres_query(
        "DROP TABLE IF EXISTS benchmark_records;"
    )

    clickhouse_query(
        """
DROP TABLE IF EXISTS ecommerce.benchmark_records
"""
    )

    manticore_sql(
        "DROP TABLE IF EXISTS benchmark_records"
    )


def benchmark_postgresql() -> dict[str, float]:
    results: dict[str, float] = {}

    prepare_postgresql()

    results["insert_one_ms"] = measure_ms(
        lambda: postgres_query(
            """
INSERT INTO benchmark_records (
    id,
    category,
    value,
    payload
)
VALUES (
    1,
    1,
    123.45,
    'single PostgreSQL benchmark record'
)
ON CONFLICT (id)
DO UPDATE SET
    value = EXCLUDED.value,
    payload = EXCLUDED.payload;
"""
        ),
        repeats=5,
        warmup=0,
    )

    postgres_query(
        "TRUNCATE TABLE benchmark_records;"
    )

    results["insert_100k_sec"] = measure_seconds(
        lambda: postgres_query(
            """
INSERT INTO benchmark_records (
    id,
    category,
    value,
    payload
)
SELECT
    g,
    1 + (g % 20),
    round(
        (
            10 + (g % 10000) * 0.25
        )::NUMERIC,
        2
    ),
    concat(
        'PostgreSQL benchmark payload ',
        g
    )
FROM generate_series(1, 100000) AS g;
""",
            timeout=600,
        )
    )

    results["select_pk_ms"] = measure_ms(
        lambda: postgres_query(
            """
SELECT
    id,
    category,
    value,
    payload
FROM benchmark_records
WHERE id = 50000;
"""
        )
    )

    update_value = 100

    def update_one() -> None:
        nonlocal update_value
        update_value += 1

        postgres_query(
            f"""
UPDATE benchmark_records
SET value = {update_value}
WHERE id = 50000;
"""
        )

    results["update_one_ms"] = measure_ms(
        update_one,
        repeats=5,
        warmup=1,
    )

    results["analytics_ms"] = measure_ms(
        lambda: postgres_query(
            """
SELECT
    c.name AS category,
    count(*) AS positions,
    sum(
        oi.quantity * oi.unit_price
    ) AS revenue
FROM order_items AS oi
JOIN products AS p
    ON p.product_id = oi.product_id
JOIN categories AS c
    ON c.category_id = p.category_id
GROUP BY c.name
ORDER BY revenue DESC;
""",
            timeout=600,
        ),
        repeats=3,
        warmup=1,
    )

    postgres_query(
        """
CREATE INDEX IF NOT EXISTS
    idx_reviews_fts_russian
ON reviews
USING GIN (
    to_tsvector(
        'russian',
        coalesce(title, '')
        || ' '
        || coalesce(body, '')
    )
);

ANALYZE reviews;
""",
        timeout=600,
    )

    results["fulltext_ms"] = measure_ms(
        lambda: postgres_query(
            """
SELECT count(*)
FROM reviews
WHERE
    to_tsvector(
        'russian',
        coalesce(title, '')
        || ' '
        || coalesce(body, '')
    )
    @@ plainto_tsquery(
        'russian',
        'качество сборки'
    );
""",
            timeout=600,
        ),
        repeats=5,
        warmup=1,
    )

    return results


def benchmark_clickhouse() -> dict[str, float]:
    results: dict[str, float] = {}

    prepare_clickhouse()

    results["insert_one_ms"] = -1.0

    clickhouse_query(
        """
TRUNCATE TABLE ecommerce.benchmark_records
"""
    )

    results["insert_100k_sec"] = measure_seconds(
        lambda: clickhouse_query(
            """
INSERT INTO ecommerce.benchmark_records
SELECT
    number + 1 AS id,
    toUInt32(1 + number % 20)
        AS category,
    toFloat64(
        10 + (number % 10000) * 0.25
    ) AS value,
    concat(
        'ClickHouse benchmark payload ',
        toString(number + 1)
    ) AS payload
FROM numbers(100000)
""",
            timeout=600,
        )
    )

    results["select_pk_ms"] = measure_ms(
        lambda: clickhouse_query(
            """
SELECT
    id,
    category,
    value,
    payload
FROM ecommerce.benchmark_records
WHERE id = 50000
FORMAT TabSeparated
"""
        )
    )

    results["analytics_ms"] = measure_ms(
        lambda: clickhouse_query(
            """
SELECT
    category,
    count() AS positions,
    round(
        sum(toFloat64(line_total)),
        2
    ) AS revenue
FROM ecommerce.orders_analytics_distributed
GROUP BY category
ORDER BY revenue DESC
FORMAT TabSeparated
""",
            timeout=600,
        ),
        repeats=5,
        warmup=1,
    )

    return results
def benchmark_manticore() -> dict[str, float]:
    results: dict[str, float] = {}

    prepare_manticore()

    single_document_id = 1

    def insert_one() -> None:
        nonlocal single_document_id

        manticore_bulk(
            [
                {
                    "id": single_document_id,
                    "payload": (
                        "single ManticoreSearch "
                        "benchmark record"
                    ),
                    "category": 1,
                    "score": 123.45,
                }
            ]
        )

        single_document_id += 1

    results["insert_one_ms"] = measure_ms(
        insert_one,
        repeats=5,
        warmup=0,
    )

    prepare_manticore()

    def insert_100k() -> None:
        inserted = 0

        while inserted < 100_000:
            batch_size = min(
                MANTICORE_BATCH_SIZE,
                100_000 - inserted,
            )

            documents: list[
                dict[str, Any]
            ] = []

            for offset in range(batch_size):
                document_id = (
                    inserted + offset + 1
                )

                documents.append(
                    {
                        "id": document_id,
                        "payload": (
                            "ManticoreSearch benchmark "
                            f"payload {document_id}"
                        ),
                        "category": (
                            1 + document_id % 20
                        ),
                        "score": (
                            10
                            + (
                                document_id % 10000
                            )
                            * 0.25
                        ),
                    }
                )

            manticore_bulk(documents)
            inserted += batch_size

    results["insert_100k_sec"] = (
        measure_seconds(insert_100k)
    )

    count_response = manticore_sql(
        """
SELECT
    COUNT(*) AS records_count
FROM benchmark_records
"""
    )

    records_count = int(
        parse_manticore_value(
            count_response,
            "records_count",
        )
    )

    if records_count != 100_000:
        raise RuntimeError(
            "Manticore benchmark count mismatch: "
            f"{records_count}"
        )

    results["select_pk_ms"] = measure_ms(
        lambda: manticore_sql(
            """
SELECT
    id,
    category,
    score
FROM benchmark_records
WHERE id = 50000
LIMIT 1
"""
        )
    )

    category_value = 100

    def update_one() -> None:
        nonlocal category_value
        category_value += 1

        manticore_sql(
            f"""
UPDATE benchmark_records
SET category = {category_value}
WHERE id = 50000
"""
        )

    results["update_one_ms"] = measure_ms(
        update_one,
        repeats=5,
        warmup=1,
    )

    results["fulltext_ms"] = measure_ms(
        lambda: manticore_sql(
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
        ),
        repeats=5,
        warmup=1,
    )

    return results


def get_storage_sizes() -> dict[str, int]:
    postgres_size = int(
        postgres_query(
            """
SELECT pg_database_size(
    current_database()
);
"""
        )
    )

    clickhouse_output = clickhouse_query(
        """
SELECT
    sum(bytes_on_disk)
FROM clusterAllReplicas(
    'cluster_2x2',
    system.parts
)
WHERE active
  AND database = 'ecommerce'
FORMAT TabSeparatedRaw
"""
    )

    clickhouse_size = int(
        clickhouse_output or "0"
    )

    _, manticore_output = run_command(
        [
            "docker",
            "exec",
            "-i",
            "group2-manticore",
            "sh",
            "-c",
            (
                "du -sk /var/lib/manticore "
                "| awk '{print $1}'"
            ),
        ],
        timeout=120,
    )

    manticore_size = (
        int(manticore_output.strip())
        * 1024
    )

    return {
        "postgresql": postgres_size,
        "clickhouse": clickhouse_size,
        "manticore": manticore_size,
    }


def format_ms(value: float) -> str:
    if value < 0:
        return "not recommended"

    return f"{value:.3f} ms"


def format_sec(value: float) -> str:
    return f"{value:.3f} sec"


def main() -> None:
    lines: list[str] = []

    lines.append(
        "PostgreSQL vs ClickHouse vs "
        "ManticoreSearch comparison"
    )

    try:
        pg_results = benchmark_postgresql()

        add_section(
            lines,
            "PostgreSQL benchmark",
            "\n".join(
                [
                    (
                        "Insert 1 record: "
                        f"{format_ms(pg_results['insert_one_ms'])}"
                    ),
                    (
                        "Insert 100K records: "
                        f"{format_sec(pg_results['insert_100k_sec'])}"
                    ),
                    (
                        "SELECT by PK: "
                        f"{format_ms(pg_results['select_pk_ms'])}"
                    ),
                    (
                        "GROUP BY on order_items: "
                        f"{format_ms(pg_results['analytics_ms'])}"
                    ),
                    (
                        "Full-text search on reviews: "
                        f"{format_ms(pg_results['fulltext_ms'])}"
                    ),
                    (
                        "UPDATE 1 record: "
                        f"{format_ms(pg_results['update_one_ms'])}"
                    ),
                ]
            ),
        )

        ch_results = benchmark_clickhouse()

        add_section(
            lines,
            "ClickHouse benchmark",
            "\n".join(
                [
                    (
                        "Insert 1 record: "
                        f"{format_ms(ch_results['insert_one_ms'])}"
                    ),
                    (
                        "Insert 100K records: "
                        f"{format_sec(ch_results['insert_100k_sec'])}"
                    ),
                    (
                        "SELECT by key: "
                        f"{format_ms(ch_results['select_pk_ms'])}"
                    ),
                    (
                        "GROUP BY on analytics rows: "
                        f"{format_ms(ch_results['analytics_ms'])}"
                    ),
                    (
                        "Full-text search: N/A"
                    ),
                    (
                        "UPDATE 1 record: "
                        "not recommended / N/A"
                    ),
                ]
            ),
        )

        manticore_results = (
            benchmark_manticore()
        )

        add_section(
            lines,
            "ManticoreSearch benchmark",
            "\n".join(
                [
                    (
                        "Insert 1 document: "
                        f"{format_ms(manticore_results['insert_one_ms'])}"
                    ),
                    (
                        "Insert 100K documents: "
                        f"{format_sec(manticore_results['insert_100k_sec'])}"
                    ),
                    (
                        "SELECT by ID: "
                        f"{format_ms(manticore_results['select_pk_ms'])}"
                    ),
                    (
                        "Analytical GROUP BY: N/A"
                    ),
                    (
                        "Full-text search on reviews: "
                        f"{format_ms(manticore_results['fulltext_ms'])}"
                    ),
                    (
                        "UPDATE 1 attribute: "
                        f"{format_ms(manticore_results['update_one_ms'])}"
                    ),
                ]
            ),
        )

        cleanup_benchmarks()

        storage_sizes = get_storage_sizes()

        comparison_lines = [
            (
                "Operation | PostgreSQL | "
                "ClickHouse | ManticoreSearch"
            ),
            (
                "--- | ---: | ---: | ---:"
            ),
            (
                "Insert 1 record | "
                f"{format_ms(pg_results['insert_one_ms'])} | "
                f"{format_ms(ch_results['insert_one_ms'])} | "
                f"{format_ms(manticore_results['insert_one_ms'])}"
            ),
            (
                "Insert 100K records | "
                f"{format_sec(pg_results['insert_100k_sec'])} | "
                f"{format_sec(ch_results['insert_100k_sec'])} | "
                f"{format_sec(manticore_results['insert_100k_sec'])}"
            ),
            (
                "SELECT by PK / ID | "
                f"{format_ms(pg_results['select_pk_ms'])} | "
                f"{format_ms(ch_results['select_pk_ms'])} | "
                f"{format_ms(manticore_results['select_pk_ms'])}"
            ),
            (
                "Analytics GROUP BY, ~1M rows | "
                f"{format_ms(pg_results['analytics_ms'])} | "
                f"{format_ms(ch_results['analytics_ms'])} | "
                "N/A"
            ),
            (
                "Full-text search, ~200K docs | "
                f"{format_ms(pg_results['fulltext_ms'])} | "
                "N/A | "
                f"{format_ms(manticore_results['fulltext_ms'])}"
            ),
            (
                "UPDATE 1 record / attribute | "
                f"{format_ms(pg_results['update_one_ms'])} | "
                "not recommended | "
                f"{format_ms(manticore_results['update_one_ms'])}"
            ),
            (
                "Size on disk | "
                f"{bytes_to_mb(storage_sizes['postgresql']):.2f} MB | "
                f"{bytes_to_mb(storage_sizes['clickhouse']):.2f} MB | "
                f"{bytes_to_mb(storage_sizes['manticore']):.2f} MB"
            ),
        ]

        add_section(
            lines,
            "Final comparison table",
            "\n".join(comparison_lines),
        )

        add_section(
            lines,
            "Storage size details",
            "\n".join(
                [
                    (
                        "PostgreSQL database size: "
                        f"{storage_sizes['postgresql']} bytes"
                    ),
                    (
                        "ClickHouse physical cluster size "
                        "including replicas: "
                        f"{storage_sizes['clickhouse']} bytes"
                    ),
                    (
                        "ManticoreSearch data directory size: "
                        f"{storage_sizes['manticore']} bytes"
                    ),
                ]
            ),
        )

        lines.append("Measurement notes:")
        lines.append(
            "- latency values are medians of repeated requests"
        )
        lines.append(
            "- bulk insertion values are measured once"
        )
        lines.append(
            "- PostgreSQL analytics uses order_items "
            "with products and categories"
        )
        lines.append(
            "- ClickHouse analytics uses "
            "orders_analytics_distributed"
        )
        lines.append(
            "- PostgreSQL full-text search uses a GIN index"
        )
        lines.append(
            "- ManticoreSearch full-text search uses "
            "the reviews RT index"
        )
        lines.append(
            "- ClickHouse size includes physical data "
            "on all replicas"
        )

    finally:
        try:
            cleanup_benchmarks()
        except Exception as cleanup_error:
            lines.append("")
            lines.append(
                f"Cleanup warning: {cleanup_error}"
            )

        OUTPUT_FILE.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

        print("\n".join(lines))


if __name__ == "__main__":
    main()