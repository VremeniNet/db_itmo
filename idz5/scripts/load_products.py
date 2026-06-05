import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


MANTICORE_HTTP = "http://localhost:9308"
ROWS_COUNT = 100_000
BATCH_SIZE = 5_000

ROOT_DIR = Path(__file__).resolve().parents[1]
CHECKS_DIR = ROOT_DIR / "checks"
OUTPUT_FILE = CHECKS_DIR / "load_products.txt"


CATEGORIES = [
    "Audio",
    "Computers",
    "Mobile",
    "Gaming",
    "Accessories",
    "Home Electronics",
]

BRANDS = [
    "Sony",
    "Samsung",
    "Apple",
    "Lenovo",
    "Asus",
    "Logitech",
    "Xiaomi",
    "JBL",
    "HyperX",
    "Dell",
]

COLORS = [
    "black",
    "white",
    "silver",
    "blue",
    "red",
]

PRODUCT_PATTERNS = [
    {
        "category": "Audio",
        "title": "Wireless Bluetooth Headphones",
        "description": "Wireless bluetooth headphones with noise cancelling, soft ear pads and long battery life.",
        "base_price": 7990,
    },
    {
        "category": "Audio",
        "title": "Noise Cancelling Headphones",
        "description": "Premium noise cancelling headphones for travel, music and online calls.",
        "base_price": 12990,
    },
    {
        "category": "Audio",
        "title": "Portable Speaker",
        "description": "Compact portable wireless speaker with bluetooth connection and strong bass.",
        "base_price": 4990,
    },
    {
        "category": "Computers",
        "title": "Laptop Pro",
        "description": "Powerful laptop for work, study and gaming with fast SSD and bright display.",
        "base_price": 54990,
    },
    {
        "category": "Mobile",
        "title": "Smart Phone",
        "description": "Modern phone with black color option, large screen and fast charging.",
        "base_price": 39990,
    },
    {
        "category": "Gaming",
        "title": "Gaming Mouse",
        "description": "Gaming mouse with RGB lighting, high precision sensor and programmable buttons.",
        "base_price": 2990,
    },
    {
        "category": "Gaming",
        "title": "Gaming Keyboard",
        "description": "Mechanical gaming keyboard with fast switches and customizable lighting.",
        "base_price": 6990,
    },
    {
        "category": "Accessories",
        "title": "USB Hub",
        "description": "Compact USB hub for laptop, phone and desktop accessories.",
        "base_price": 1990,
    },
    {
        "category": "Home Electronics",
        "title": "Smart Home Camera",
        "description": "Smart camera for home security with mobile app and night mode.",
        "base_price": 5990,
    },
    {
        "category": "Computers",
        "title": "Gaming Laptop",
        "description": "Gaming laptop with powerful graphics card, cooling system and fast processor.",
        "base_price": 74990,
    },
]


def http_post(path: str, body: str, content_type: str = "application/x-www-form-urlencoded") -> str:
    request = urllib.request.Request(
        url=f"{MANTICORE_HTTP}{path}",
        data=body.encode("utf-8"),
        headers={"Content-Type": content_type},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8", errors="replace")


def sql(query: str) -> str:
    body = urllib.parse.urlencode({"query": query})
    return http_post("/sql?mode=raw", body)


def bulk_insert(documents: list[dict]) -> str:
    lines = []

    for document in documents:
        action = {
            "insert": {
                "index": "products",
                "id": document["id"],
                "doc": document["doc"],
            }
        }
        lines.append(json.dumps(action, ensure_ascii=False))

    body = "\n".join(lines) + "\n"
    return http_post("/bulk", body, content_type="application/x-ndjson")


def build_product(product_id: int) -> dict:
    pattern = PRODUCT_PATTERNS[product_id % len(PRODUCT_PATTERNS)]

    brand = BRANDS[product_id % len(BRANDS)]
    color = COLORS[product_id % len(COLORS)]

    price = float(pattern["base_price"] + (product_id % 2500))
    rating = round(3.5 + ((product_id % 16) / 10), 1)

    if rating > 5.0:
        rating = 5.0

    reviews_count = int(10 + (product_id % 5000))
    in_stock = product_id % 7 != 0

    title = f"{brand} {pattern['title']} {product_id}"

    description = (
        f"<p>{pattern['description']}</p> "
        f"<p>Brand: {brand}. Color: {color}. "
        f"This product is suitable for online shopping, delivery and customer reviews.</p>"
    )

    tags = {
        "color": color,
        "warranty": "12 months",
        "delivery": "standard" if product_id % 3 else "express",
        "origin": "generated",
    }

    created_at = int(time.time()) - (product_id % 10_000)

    return {
        "id": product_id,
        "doc": {
            "title": title,
            "description": description,
            "category": pattern["category"],
            "brand": brand,
            "price": price,
            "rating": rating,
            "reviews_count": reviews_count,
            "in_stock": in_stock,
            "tags": tags,
            "created_at": created_at,
        },
    }


def main() -> None:
    CHECKS_DIR.mkdir(exist_ok=True)

    output = []
    output.append("Product data loading into ManticoreSearch")
    output.append("")
    output.append(f"Rows requested: {ROWS_COUNT}")
    output.append("")

    output.append("=" * 80)
    output.append("Clean products index")
    output.append("=" * 80)

    try:
        truncate_result = sql("TRUNCATE RTINDEX products")
    except Exception as error:
        truncate_result = f"TRUNCATE failed: {error}"

    output.append(truncate_result)
    output.append("")

    started_at = time.perf_counter()
    inserted = 0

    output.append("=" * 80)
    output.append("Bulk insert")
    output.append("=" * 80)

    for batch_start in range(1, ROWS_COUNT + 1, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE - 1, ROWS_COUNT)

        documents = [
            build_product(product_id)
            for product_id in range(batch_start, batch_end + 1)
        ]

        result = bulk_insert(documents)

        try:
            parsed = json.loads(result)
            errors = parsed.get("errors")
            if errors:
                output.append(f"Batch {batch_start}-{batch_end}: errors = {errors}")
                output.append(result[:1000])
            else:
                output.append(f"Batch {batch_start}-{batch_end}: ok")
        except json.JSONDecodeError:
            output.append(f"Batch {batch_start}-{batch_end}: raw response")
            output.append(result[:1000])

        inserted += len(documents)

    elapsed = time.perf_counter() - started_at

    output.append("")
    output.append("=" * 80)
    output.append("Final count")
    output.append("=" * 80)

    count_result = sql("SELECT COUNT(*) AS products_count FROM products")
    output.append(count_result)
    output.append("")
    output.append(f"Rows generated by script: {inserted}")
    output.append(f"Elapsed time: {elapsed:.3f} sec")

    OUTPUT_FILE.write_text("\n".join(output), encoding="utf-8")
    print("\n".join(output))


if __name__ == "__main__":
    main()