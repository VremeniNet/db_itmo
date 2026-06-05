import time
import urllib.parse
import urllib.request
from pathlib import Path


MANTICORE_HTTP = "http://localhost:9308"

ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"


QUERIES = [
    {
        "name": "4.1 Basic search",
        "file": "basic_search.txt",
        "sql": """
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('wireless bluetooth headphones')
ORDER BY w DESC
LIMIT 10
""",
    },
    {
        "name": "4.2 Exact phrase search",
        "file": "phrase_search.txt",
        "sql": """
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('"noise cancelling"')
ORDER BY w DESC
LIMIT 10
""",
    },
    {
        "name": "4.3 Proximity search",
        "file": "proximity_search.txt",
        "sql": """
SELECT id, title, WEIGHT() AS w
FROM products
WHERE MATCH('"portable speaker"~3')
ORDER BY w DESC
LIMIT 10
""",
    },
    {
        "name": "4.4 Search with attribute filters",
        "file": "filtered_search.txt",
        "sql": """
SELECT id, title, price, rating
FROM products
WHERE MATCH('laptop')
  AND price BETWEEN 30000 AND 80000
  AND rating >= 4.0
ORDER BY rating DESC
LIMIT 10
""",
    },
    {
        "name": "4.5 Search by JSON attribute",
        "file": "json_search.txt",
        "sql": """
SELECT id, title, tags
FROM products
WHERE MATCH('phone')
  AND tags.color = 'black'
LIMIT 10
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

    for item in QUERIES:
        output_file = CHECKS_DIR / item["file"]

        lines = []
        lines.append(item["name"])
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

        output_file.write_text("\n".join(lines), encoding="utf-8")
        print(f"{item['file']}: done")


if __name__ == "__main__":
    main()