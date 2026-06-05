import time
import urllib.parse
import urllib.request
from pathlib import Path


MANTICORE_HTTP = "http://localhost:9308"

ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
OUTPUT_FILE = CHECKS_DIR / "facets.txt"


QUERIES = [
    {
        "name": "1. Aggregation by category",
        "sql": """
SELECT
    category,
    COUNT(*) AS cnt,
    AVG(price) AS avg_price
FROM products
WHERE MATCH('gaming')
GROUP BY category
ORDER BY cnt DESC
""",
    },
    {
        "name": "2. FACET by category and brand",
        "sql": """
SELECT id, title, price
FROM products
WHERE MATCH('gaming')
LIMIT 10
FACET category ORDER BY COUNT(*) DESC
FACET brand ORDER BY COUNT(*) DESC
""",
    },
]


def run_sql(query: str) -> tuple[str, float]:
    body = urllib.parse.urlencode({"query": query})

    request = urllib.request.Request(
        url=f"{MANTICORE_HTTP}/sql?mode=raw",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    started_at = time.perf_counter()

    with urllib.request.urlopen(request, timeout=120) as response:
        result = response.read().decode("utf-8", errors="replace")

    elapsed = time.perf_counter() - started_at
    return result.strip(), elapsed


def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    lines = []
    lines.append("Faceted search and aggregations")
    lines.append("")

    for item in QUERIES:
        lines.append("=" * 80)
        lines.append(item["name"])
        lines.append("=" * 80)
        lines.append("")
        lines.append("SQL:")
        lines.append(item["sql"].strip())
        lines.append("")
        lines.append("Result:")

        try:
            result, elapsed = run_sql(item["sql"])
            lines.append(result)
            lines.append("")
            lines.append(f"Elapsed time: {elapsed:.4f} sec")
        except Exception as error:
            lines.append(f"ERROR: {error}")

        lines.append("")

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()