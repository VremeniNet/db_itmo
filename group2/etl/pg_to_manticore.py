import csv
import io
import json
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]

POSTGRES_CONTAINER = "group2-postgres"
MANTICORE_HTTP = "http://127.0.0.1:19308"

BATCH_SIZE = 2_000

ETL_OUTPUT_FILE = (
    ROOT_DIR
    / "checks"
    / "etl_sync.txt"
)

SEARCH_OUTPUT_FILE = (
    ROOT_DIR
    / "checks"
    / "manticore_search.txt"
)

CREATE_INDEX_FILE = (
    ROOT_DIR
    / "sql"
    / "manticore"
    / "01_create_index.sql"
)

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)

COPY_SQL = """
COPY (
    SELECT
        review_id,
        title,
        body,
        product_id,
        customer_id,
        rating,
        extract(epoch FROM created_at)::BIGINT
            AS created_at
    FROM reviews
    ORDER BY review_id
) TO STDOUT WITH (
    FORMAT CSV
)
"""

SEARCH_QUERIES = [
    {
        "title": "1. Full-text search",
        "sql": """
SELECT
    id,
    title,
    rating,
    WEIGHT() AS weight
FROM reviews
WHERE MATCH('отличный товар рекомендую')
ORDER BY weight DESC
LIMIT 10
""",
    },
    {
        "title": "2. Attribute filtering",
        "sql": """
SELECT
    id,
    title,
    product_id,
    rating
FROM reviews
WHERE rating >= 4
  AND product_id = 42
ORDER BY
    rating DESC,
    id
LIMIT 20
""",
    },
    {
        "title": "3. Facet by rating",
        "sql": """
SELECT
    id,
    title,
    rating
FROM reviews
WHERE MATCH('товар')
LIMIT 10
FACET rating
ORDER BY COUNT(*) DESC
""",
    },
    {
        "title": "4. Negative reviews search",
        "sql": """
SELECT
    id,
    title,
    rating,
    WEIGHT() AS weight
FROM reviews
WHERE MATCH('брак сломался возврат')
ORDER BY weight DESC
LIMIT 10
""",
    },
]


def manticore_request(
    path: str,
    body: bytes,
    content_type: str,
    timeout: int = 120,
) -> str:
    request = urllib.request.Request(
        url=f"{MANTICORE_HTTP}{path}",
        data=body,
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


def manticore_sql(query: str) -> str:
    body = urllib.parse.urlencode(
        {"query": query}
    ).encode("utf-8")

    return manticore_request(
        "/sql?mode=raw",
        body,
        "application/x-www-form-urlencoded",
    )


def execute_sql_file(path: Path) -> None:
    source = path.read_text(encoding="utf-8")

    clean_lines = [
        line
        for line in source.splitlines()
        if not line.strip().startswith("--")
    ]

    clean_source = "\n".join(clean_lines)

    statements = [
        statement.strip()
        for statement in clean_source.split(";")
        if statement.strip()
    ]

    for statement in statements:
        manticore_sql(statement)


def postgres_count() -> int:
    result = subprocess.run(
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
            "SELECT count(*) FROM reviews;",
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

    return int(result.stdout.strip())


def bulk_insert(documents: list[dict[str, Any]]) -> None:
    lines: list[str] = []

    for document in documents:
        lines.append(
            json.dumps(
                {
                    "insert": {
                        "index": "reviews",
                        "id": document["id"],
                        "doc": document["doc"],
                    }
                },
                ensure_ascii=False,
            )
        )

    body = (
        "\n".join(lines) + "\n"
    ).encode("utf-8")

    response = manticore_request(
        "/bulk",
        body,
        "application/x-ndjson",
        timeout=180,
    )

    parsed = json.loads(response)

    if parsed.get("errors"):
        raise RuntimeError(
            "Manticore bulk request returned errors:\n"
            + response[:3000]
        )


def export_and_load_reviews() -> tuple[int, int, float]:
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

    process = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if process.stdout is None:
        raise RuntimeError(
            "PostgreSQL stdout is unavailable"
        )

    started_at = time.perf_counter()

    stream = io.TextIOWrapper(
        process.stdout,
        encoding="utf-8",
        newline="",
    )

    reader = csv.reader(stream)

    batch: list[dict[str, Any]] = []
    inserted = 0
    batches = 0

    for row in reader:
        if len(row) != 7:
            raise RuntimeError(
                f"Unexpected PostgreSQL row: {row}"
            )

        document = {
            "id": int(row[0]),
            "doc": {
                "title": row[1],
                "body": row[2],
                "product_id": int(row[3]),
                "customer_id": int(row[4]),
                "rating": int(row[5]),
                "created_at": int(row[6]),
            },
        }

        batch.append(document)

        if len(batch) >= BATCH_SIZE:
            bulk_insert(batch)
            inserted += len(batch)
            batches += 1
            batch = []

            if batches % 10 == 0:
                print(
                    f"Loaded {inserted} reviews"
                )

    if batch:
        bulk_insert(batch)
        inserted += len(batch)
        batches += 1

    return_code = process.wait(timeout=120)

    stderr = b""

    if process.stderr is not None:
        stderr = process.stderr.read()

    if return_code != 0:
        raise RuntimeError(
            "PostgreSQL export failed:\n"
            + stderr.decode(
                "utf-8",
                errors="replace",
            )
        )

    elapsed = time.perf_counter() - started_at

    return inserted, batches, elapsed


def parse_count(response: str) -> int:
    parsed = json.loads(response)

    # ManticoreSearch mode=raw обычно возвращает
    # массив наборов результатов.
    if isinstance(parsed, list):
        if not parsed:
            raise RuntimeError(
                f"Count query returned an empty list: {response}"
            )

        result_set = parsed[0]
    else:
        result_set = parsed

    if not isinstance(result_set, dict):
        raise RuntimeError(
            f"Unexpected count response format: {response}"
        )

    data = result_set.get("data", [])

    if not data:
        raise RuntimeError(
            f"Count query returned no data: {response}"
        )

    first_row = data[0]

    if isinstance(first_row, dict):
        for key in (
            "reviews_count",
            "count(*)",
            "count()",
        ):
            if key in first_row:
                return int(first_row[key])

    if isinstance(first_row, list) and first_row:
        return int(first_row[0])

    raise RuntimeError(
        f"Cannot extract count from response: {response}"
    )


def replace_manticore_etl_section(
    content: str,
) -> None:
    marker = (
        "\n\n"
        + "=" * 80
        + "\nPostgreSQL to ManticoreSearch ETL\n"
        + "=" * 80
    )

    existing = ""

    if ETL_OUTPUT_FILE.exists():
        existing = ETL_OUTPUT_FILE.read_text(
            encoding="utf-8"
        )

    if marker in existing:
        existing = existing.split(marker, 1)[0]

    final_content = (
        existing.rstrip()
        + marker
        + "\n"
        + content.strip()
        + "\n"
    )

    ETL_OUTPUT_FILE.write_text(
        final_content,
        encoding="utf-8",
    )


def run_searches() -> None:
    lines: list[str] = []

    lines.append(
        "ManticoreSearch review queries"
    )

    for item in SEARCH_QUERIES:
        lines.append("")
        lines.append("=" * 80)
        lines.append(item["title"])
        lines.append("=" * 80)
        lines.append("")
        lines.append("SQL:")
        lines.append(item["sql"].strip())
        lines.append("")
        lines.append("Result:")

        started_at = time.perf_counter()
        response = manticore_sql(item["sql"])
        elapsed = time.perf_counter() - started_at

        lines.append(response)
        lines.append("")
        lines.append(
            f"Elapsed time: {elapsed:.4f} sec"
        )

    SEARCH_OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    source_count = postgres_count()

    execute_sql_file(CREATE_INDEX_FILE)

    inserted, batches, elapsed = (
        export_and_load_reviews()
    )

    count_response = manticore_sql(
        """
SELECT
    COUNT(*) AS reviews_count
FROM reviews
"""
    )

    target_count = parse_count(count_response)

    if inserted != source_count:
        raise RuntimeError(
            "Inserted row count does not match "
            f"PostgreSQL: {inserted} != {source_count}"
        )

    if target_count != source_count:
        raise RuntimeError(
            "Manticore row count does not match "
            f"PostgreSQL: {target_count} != {source_count}"
        )

    etl_content = f"""
PostgreSQL source reviews: {source_count}
ManticoreSearch inserted reviews: {inserted}
ManticoreSearch final count: {target_count}
Batch size: {BATCH_SIZE}
Batches: {batches}
Load elapsed time: {elapsed:.3f} sec

Count response:
{count_response}
"""

    replace_manticore_etl_section(etl_content)
    run_searches()

    print(etl_content.strip())
    print("")
    print(
        f"Search results saved to: "
        f"{SEARCH_OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()