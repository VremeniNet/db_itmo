import subprocess
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

OUTPUT_FILE = (
    ROOT_DIR
    / "checks"
    / "pg_oltp.txt"
)

POSTGRES_CONTAINER = "group2-postgres"
POSTGRES_DATABASE = "ecommerce"
POSTGRES_USER = "postgres"


def run_psql(
    sql: str,
    timeout: int,
) -> tuple[str, float]:
    started_at = time.perf_counter()

    result = subprocess.run(
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
            POSTGRES_USER,
            "-d",
            POSTGRES_DATABASE,
        ],
        cwd=ROOT_DIR,
        input=sql,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )

    elapsed = time.perf_counter() - started_at
    output = result.stdout.strip()

    if result.returncode != 0:
        raise RuntimeError(
            f"psql returned code {result.returncode}\n"
            f"{output}"
        )

    return output, elapsed


def add_section(
    lines: list[str],
    title: str,
    output: str,
    elapsed: float,
) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)
    lines.append(output)
    lines.append("")
    lines.append(
        f"Elapsed time: {elapsed:.3f} sec"
    )


def main() -> None:
    sql_dir = ROOT_DIR / "sql" / "pg"

    schema_sql = (
        sql_dir / "01_schema.sql"
    ).read_text(encoding="utf-8")

    seed_sql = (
        sql_dir / "02_seed_data.sql"
    ).read_text(encoding="utf-8")

    oltp_sql = (
        sql_dir / "03_oltp_queries.sql"
    ).read_text(encoding="utf-8")

    lines: list[str] = []

    lines.append(
        "PostgreSQL OLTP schema, data and operations"
    )

    schema_output, schema_elapsed = run_psql(
        schema_sql,
        timeout=300,
    )

    add_section(
        lines,
        "1. Create normalized schema",
        schema_output,
        schema_elapsed,
    )

    seed_output, seed_elapsed = run_psql(
        seed_sql,
        timeout=1800,
    )

    add_section(
        lines,
        "2. Generate test data",
        seed_output,
        seed_elapsed,
    )

    oltp_output, oltp_elapsed = run_psql(
        oltp_sql,
        timeout=300,
    )

    add_section(
        lines,
        "3. OLTP operations",
        oltp_output,
        oltp_elapsed,
    )

    verification_sql = """
SELECT
    count(*) AS orders_count
FROM orders;

SELECT
    count(*) AS reviews_count
FROM reviews;

SELECT
    count(*) AS order_items_count
FROM order_items;

SELECT
    pg_size_pretty(
        pg_database_size(current_database())
    ) AS database_size;
"""

    verification_output, verification_elapsed = (
        run_psql(
            verification_sql,
            timeout=120,
        )
    )

    add_section(
        lines,
        "4. Final verification",
        verification_output,
        verification_elapsed,
    )

    OUTPUT_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("\n".join(lines))


if __name__ == "__main__":
    main()