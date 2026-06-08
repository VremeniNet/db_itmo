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
OUTPUT_FILE = ROOT_DIR / "checks" / "demo_output.txt"

POSTGRES_CONTAINER = "group2-postgres"
CLICKHOUSE_MAIN = "group2-ch-s1-r1"

CLICKHOUSE_NODES = [
    "group2-ch-s1-r1",
    "group2-ch-s1-r2",
    "group2-ch-s2-r1",
    "group2-ch-s2-r2",
]

MANTICORE_HTTP = "http://127.0.0.1:19308"

NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)


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
            f"Command failed with code {result.returncode}:\n"
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

    return output


def postgres_copy(sql: str) -> bytes:
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
            sql,
        ],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(
                "utf-8",
                errors="replace",
            )
        )

    return result.stdout


def clickhouse_query(
    sql: str,
    container: str = CLICKHOUSE_MAIN,
    timeout: int = 180,
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


def clickhouse_insert_csv(csv_data: bytes) -> str:
    result = subprocess.run(
        [
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
        ],
        cwd=ROOT_DIR,
        input=csv_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
    )

    output = result.stdout.decode(
        "utf-8",
        errors="replace",
    ).strip()

    if result.returncode != 0:
        raise RuntimeError(
            f"ClickHouse insert failed:\n{output}"
        )

    return output or "Order rows inserted into ClickHouse."


def sync_clickhouse_replicas() -> str:
    lines: list[str] = []

    tables = [
        "orders_analytics_local",
        "category_revenue_local",
        "daily_orders_local",
    ]

    for container in CLICKHOUSE_NODES:
        for table in tables:
            code, output = clickhouse_query(
                (
                    "SYSTEM SYNC REPLICA "
                    f"ecommerce.{table}"
                ),
                container=container,
                timeout=180,
                check=False,
            )

            lines.append(
                f"{container} / {table}: "
                f"code={code}, "
                f"result={output or 'synchronized'}"
            )

    return "\n".join(lines)


def manticore_request(
    path: str,
    body: bytes,
    content_type: str,
    timeout: int = 120,
) -> str:
    request = urllib.request.Request(
        f"{MANTICORE_HTTP}{path}",
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


def manticore_sql(sql: str) -> str:
    body = urllib.parse.urlencode(
        {"query": sql}
    ).encode("utf-8")

    return manticore_request(
        "/sql?mode=raw",
        body,
        "application/x-www-form-urlencoded",
    )


def manticore_insert_review(
    review: dict[str, Any],
) -> str:
    payload = {
        "insert": {
            "index": "reviews",
            "id": review["id"],
            "doc": {
                "title": review["title"],
                "body": review["body"],
                "product_id": review["product_id"],
                "customer_id": review["customer_id"],
                "rating": review["rating"],
                "created_at": review["created_at"],
            },
        }
    }

    body = (
        json.dumps(
            payload,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")

    response = manticore_request(
        "/bulk",
        body,
        "application/x-ndjson",
    )

    parsed = json.loads(response)

    if parsed.get("errors"):
        raise RuntimeError(
            f"Manticore insert failed:\n{response}"
        )

    return response


def create_order() -> int:
    sql = """
WITH new_order AS (
    INSERT INTO orders (
        customer_id,
        order_date,
        status
    )
    VALUES (
        42,
        now(),
        'new'
    )
    RETURNING order_id
),
inserted_items AS (
    INSERT INTO order_items (
        order_id,
        product_id,
        quantity,
        unit_price
    )
    SELECT
        new_order.order_id,
        products.product_id,
        requested.quantity,
        products.price
    FROM new_order
    CROSS JOIN (
        VALUES
            (42::BIGINT, 2::INTEGER),
            (142::BIGINT, 1::INTEGER)
    ) AS requested(product_id, quantity)
    JOIN products
        ON products.product_id = requested.product_id
    RETURNING order_id
)
SELECT min(order_id)
FROM inserted_items;
"""

    output = postgres_query(sql)

    return int(output.strip())


def export_order(order_id: int) -> bytes:
    sql = f"""
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
    WHERE o.order_id = {order_id}
    ORDER BY oi.order_item_id
) TO STDOUT WITH (
    FORMAT CSV
)
"""

    return postgres_copy(sql)


def create_review() -> int:
    sql = """
INSERT INTO reviews (
    product_id,
    customer_id,
    rating,
    title,
    body,
    created_at
)
VALUES (
    42,
    42,
    5,
    'Качество сборки',
    'Отличное качество сборки. '
        'Товар надёжный, удобный и полностью '
        'соответствует описанию.',
    now()
)
RETURNING review_id;
"""

    return int(postgres_query(sql).strip())


def export_review(review_id: int) -> dict[str, Any]:
    sql = f"""
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
    WHERE review_id = {review_id}
) TO STDOUT WITH (
    FORMAT CSV
)
"""

    csv_data = postgres_copy(sql)

    text_stream = io.StringIO(
        csv_data.decode("utf-8")
    )

    row = next(csv.reader(text_stream))

    return {
        "id": int(row[0]),
        "title": row[1],
        "body": row[2],
        "product_id": int(row[3]),
        "customer_id": int(row[4]),
        "rating": int(row[5]),
        "created_at": int(row[6]),
    }


def add_section(
    lines: list[str],
    title: str,
    content: str,
    elapsed: float | None = None,
) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)
    lines.append(content)

    if elapsed is not None:
        lines.append("")
        lines.append(
            f"Elapsed time: {elapsed:.4f} sec"
        )

    lines.append("")


def main() -> None:
    lines: list[str] = []

    lines.append(
        "Multi-DB end-to-end demo scenario"
    )

    # ------------------------------------------------------------
    # 1. Создание заказа в PostgreSQL
    # ------------------------------------------------------------

    started_at = time.perf_counter()
    order_id = create_order()
    elapsed = time.perf_counter() - started_at

    order_details = postgres_query(
        f"""
SELECT
    o.order_id,
    o.status,
    c.full_name,
    c.region,
    count(oi.order_item_id) AS positions,
    sum(oi.quantity) AS items,
    round(
        sum(oi.quantity * oi.unit_price),
        2
    ) AS order_total
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.order_id = {order_id}
GROUP BY
    o.order_id,
    o.status,
    c.full_name,
    c.region;
"""
    )

    add_section(
        lines,
        "1. Create order in PostgreSQL",
        (
            f"Created order_id: {order_id}\n\n"
            f"{order_details}"
        ),
        elapsed,
    )

    # ------------------------------------------------------------
    # 2. Инкрементальный ETL заказа в ClickHouse
    # ------------------------------------------------------------

    started_at = time.perf_counter()

    order_csv = export_order(order_id)
    insert_result = clickhouse_insert_csv(
        order_csv
    )

    _, flush_result = clickhouse_query(
        """
SYSTEM FLUSH DISTRIBUTED
ecommerce.orders_analytics_distributed
"""
    )

    sync_result = sync_clickhouse_replicas()

    elapsed = time.perf_counter() - started_at

    add_section(
        lines,
        "2. Incremental ETL PostgreSQL to ClickHouse",
        (
            f"{insert_result}\n"
            f"{flush_result or 'Distributed queue flushed.'}"
            f"\n\n{sync_result}"
        ),
        elapsed,
    )

    # ------------------------------------------------------------
    # 3. Аналитика ClickHouse
    # ------------------------------------------------------------

    _, order_check = clickhouse_query(
        f"""
SELECT
    order_id,
    count() AS positions,
    sum(quantity) AS items,
    round(sum(toFloat64(line_total)), 2)
        AS order_total,
    any(order_status) AS order_status
FROM ecommerce.orders_analytics_distributed
WHERE order_id = {order_id}
GROUP BY order_id
FORMAT PrettyCompact
"""
    )

    started_at = time.perf_counter()

    _, top_categories = clickhouse_query(
        """
WITH
    (
        SELECT max(order_date)
        FROM ecommerce.orders_analytics_distributed
    ) AS max_order_date
SELECT
    category,
    round(sumMerge(revenue), 2)
        AS total_revenue,
    sumMerge(quantity) AS items_sold
FROM ecommerce.category_revenue_distributed
WHERE order_date >= toStartOfMonth(max_order_date)
  AND order_date <= max_order_date
GROUP BY category
ORDER BY total_revenue DESC
LIMIT 5
FORMAT PrettyCompact
"""
    )

    elapsed = time.perf_counter() - started_at

    add_section(
        lines,
        "3. ClickHouse analytics",
        (
            "New order in ClickHouse:\n"
            f"{order_check}\n\n"
            "Top 5 categories by revenue "
            "in the latest month:\n"
            f"{top_categories}"
        ),
        elapsed,
    )

    # ------------------------------------------------------------
    # 4. Создание отзыва в PostgreSQL
    # ------------------------------------------------------------

    started_at = time.perf_counter()
    review_id = create_review()
    elapsed = time.perf_counter() - started_at

    review_details = postgres_query(
        f"""
SELECT
    review_id,
    product_id,
    customer_id,
    rating,
    title,
    body
FROM reviews
WHERE review_id = {review_id};
"""
    )

    add_section(
        lines,
        "4. Create review in PostgreSQL",
        (
            f"Created review_id: {review_id}\n\n"
            f"{review_details}"
        ),
        elapsed,
    )

    # ------------------------------------------------------------
    # 5. Инкрементальный ETL в ManticoreSearch
    # ------------------------------------------------------------

    started_at = time.perf_counter()

    review = export_review(review_id)
    manticore_insert_result = (
        manticore_insert_review(review)
    )

    elapsed = time.perf_counter() - started_at

    direct_review_check = manticore_sql(
        f"""
SELECT
    id,
    title,
    product_id,
    customer_id,
    rating
FROM reviews
WHERE id = {review_id}
LIMIT 1
"""
    )

    add_section(
        lines,
        "5. Incremental ETL PostgreSQL to ManticoreSearch",
        (
            f"Bulk response:\n"
            f"{manticore_insert_result}\n\n"
            f"Inserted review verification:\n"
            f"{direct_review_check}"
        ),
        elapsed,
    )

    # ------------------------------------------------------------
    # 6. Полнотекстовый поиск
    # ------------------------------------------------------------

    started_at = time.perf_counter()

    search_result = manticore_sql(
        """
SELECT
    id,
    title,
    product_id,
    rating,
    WEIGHT() AS weight
FROM reviews
WHERE MATCH('качество сборки')
ORDER BY id DESC
LIMIT 10
"""
    )

    elapsed = time.perf_counter() - started_at

    add_section(
        lines,
        "6. Full-text search in ManticoreSearch",
        (
            "Search query: качество сборки\n\n"
            f"{search_result}"
        ),
        elapsed,
    )

    lines.append("")
    lines.append("Demo summary:")
    lines.append(
        f"- PostgreSQL order_id: {order_id}"
    )
    lines.append(
        "- order was incrementally loaded "
        "into ClickHouse"
    )
    lines.append(
        "- ClickHouse analytical query succeeded"
    )
    lines.append(
        f"- PostgreSQL review_id: {review_id}"
    )
    lines.append(
        "- review was incrementally loaded "
        "into ManticoreSearch"
    )
    lines.append(
        "- full-text search returned the new review"
    )

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))


if __name__ == "__main__":
    main()