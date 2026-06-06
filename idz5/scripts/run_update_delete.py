import time
import urllib.parse
import urllib.request
from pathlib import Path


MANTICORE_HTTP = "http://localhost:9308"

ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
OUTPUT_FILE = CHECKS_DIR / "update_delete.txt"


STEPS = [
    {
        "name": "1. Product before UPDATE",
        "sql": """
SELECT id, title, price, rating
FROM products
WHERE id = 4
""",
    },
    {
        "name": "2. UPDATE price and rating",
        "sql": """
UPDATE products
SET price = 29999, rating = 4.9
WHERE id = 4
""",
    },
    {
        "name": "3. Product after UPDATE",
        "sql": """
SELECT id, title, price, rating
FROM products
WHERE id = 4
""",
    },
    {
        "name": "4. Insert document for DELETE demo",
        "sql": """
REPLACE INTO products (
    id,
    title,
    description,
    category,
    brand,
    price,
    rating,
    reviews_count,
    in_stock,
    tags,
    created_at
)
VALUES (
    200001,
    'Delete Demo Unique Headphones',
    'Temporary product for delete demonstration with unique delete marker.',
    'Audio',
    'DemoBrand',
    9999,
    4.5,
    10,
    1,
    '{"color":"black","origin":"delete_demo"}',
    1735689600
)
""",
    },
    {
        "name": "5. Search document before DELETE",
        "sql": """
SELECT id, title
FROM products
WHERE MATCH('delete demo unique')
LIMIT 10
""",
    },
    {
        "name": "6. DELETE document",
        "sql": """
DELETE FROM products
WHERE id = 200001
""",
    },
    {
        "name": "7. Search document after DELETE",
        "sql": """
SELECT id, title
FROM products
WHERE MATCH('delete demo unique')
LIMIT 10
""",
    },
    {
        "name": "8. Insert old document for REPLACE demo",
        "sql": """
REPLACE INTO products (
    id,
    title,
    description,
    category,
    brand,
    price,
    rating,
    reviews_count,
    in_stock,
    tags,
    created_at
)
VALUES (
    200002,
    'Replace Demo Old Product',
    'Old version of product before replace operation.',
    'Accessories',
    'DemoBrand',
    1000,
    3.0,
    1,
    1,
    '{"color":"white","version":"old"}',
    1735689600
)
""",
    },
    {
        "name": "9. Document before REPLACE",
        "sql": """
SELECT id, title, price, rating, tags
FROM products
WHERE id = 200002
""",
    },
    {
        "name": "10. REPLACE document with new content",
        "sql": """
REPLACE INTO products (
    id,
    title,
    description,
    category,
    brand,
    price,
    rating,
    reviews_count,
    in_stock,
    tags,
    created_at
)
VALUES (
    200002,
    'Replace Demo New Product',
    'New version of product after replace operation.',
    'Accessories',
    'DemoBrand',
    2500,
    4.8,
    25,
    1,
    '{"color":"blue","version":"new"}',
    1735689600
)
""",
    },
    {
        "name": "11. Document after REPLACE",
        "sql": """
SELECT id, title, price, rating, tags
FROM products
WHERE id = 200002
""",
    },
    {
        "name": "12. Search old content after REPLACE",
        "sql": """
SELECT id, title
FROM products
WHERE MATCH('replace demo old')
LIMIT 10
""",
    },
    {
        "name": "13. Search new content after REPLACE",
        "sql": """
SELECT id, title
FROM products
WHERE MATCH('replace demo new')
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

    lines = []
    lines.append("UPDATE / DELETE / REPLACE demo in ManticoreSearch")
    lines.append("")

    for step in STEPS:
        lines.append("=" * 80)
        lines.append(step["name"])
        lines.append("=" * 80)
        lines.append("")
        lines.append("SQL:")
        lines.append(step["sql"].strip())
        lines.append("")
        lines.append("Result:")

        try:
            result, elapsed = run_sql(step["sql"])
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