from datetime import date, timedelta
from pathlib import Path
import random


random.seed(4150)

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_FILE = BASE_DIR / "sql" / "00_orders_raw.sql"

CUSTOMERS = [
    ("Иванов Иван Иванович", "ivanov@example.com", "+79990000001"),
    ("Петров Петр Петрович", "petrov@example.com", "+79990000002"),
    ("Сидорова Анна Сергеевна", "sidorova@example.com", "+79990000003"),
    ("Кузнецов Алексей Олегович", "kuznetsov@example.com", "+79990000004"),
    ("Смирнова Мария Андреевна", "smirnova@example.com", "+79990000005"),
    ("Васильев Дмитрий Игоревич", "vasiliev@example.com", "+79990000006"),
    ("Морозова Елена Павловна", "morozova@example.com", "+79990000007"),
    ("Новиков Артем Максимович", "novikov@example.com", "+79990000008"),
    ("Федорова Ольга Николаевна", "fedorova@example.com", "+79990000009"),
    ("Соколов Кирилл Денисович", "sokolov@example.com", "+79990000010"),
]

ADDRESSES = [
    "Санкт-Петербург, Невский проспект, д. 10",
    "Санкт-Петербург, Литейный проспект, д. 25",
    "Москва, ул. Тверская, д. 7",
    "Казань, ул. Баумана, д. 14",
    "Новосибирск, Красный проспект, д. 31",
    "Екатеринбург, ул. Малышева, д. 44",
    "Санкт-Петербург, Московский проспект, д. 120",
    "Нижний Новгород, ул. Большая Покровская, д. 18",
]

PRODUCTS = [
    ("Ноутбук", 85000),
    ("Мышь", 1500),
    ("Коврик", 500),
    ("Монитор", 22000),
    ("Кабель HDMI", 900),
    ("Клавиатура", 3500),
    ("Наушники", 6000),
    ("Веб-камера", 4500),
    ("Внешний SSD", 12000),
    ("USB-хаб", 2500),
]

STATUSES = ["new", "processing", "shipped", "delivered", "cancelled"]


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def generate_order(order_id: int) -> str:
    customer_name, customer_email, customer_phone = random.choice(CUSTOMERS)
    delivery_address = random.choice(ADDRESSES)

    order_date = date(2024, 1, 1) + timedelta(days=random.randint(0, 364))
    status = random.choice(STATUSES)

    items_count = random.randint(1, 4)
    items = random.sample(PRODUCTS, items_count)

    names = []
    prices = []
    quantities = []
    total_amount = 0

    for product_name, product_price in items:
        quantity = random.randint(1, 3)

        names.append(product_name)
        prices.append(str(product_price))
        quantities.append(str(quantity))

        total_amount += product_price * quantity

    values = [
        str(order_id),
        sql_string(order_date.isoformat()),
        sql_string(customer_name),
        sql_string(customer_email),
        sql_string(customer_phone),
        sql_string(delivery_address),
        sql_string(", ".join(names)),
        sql_string(", ".join(prices)),
        sql_string(", ".join(quantities)),
        str(total_amount),
        sql_string(status),
    ]

    return "(" + ", ".join(values) + ")"


def main() -> None:
    rows = [generate_order(order_id) for order_id in range(1, 1201)]

    sql = """DROP TABLE IF EXISTS orders_raw;

CREATE TABLE orders_raw (
    order_id INTEGER,
    order_date DATE,
    customer_name TEXT,
    customer_email TEXT,
    customer_phone TEXT,
    delivery_address TEXT,
    product_names TEXT,
    product_prices TEXT,
    product_quantities TEXT,
    total_amount NUMERIC,
    status TEXT
);

INSERT INTO orders_raw (
    order_id,
    order_date,
    customer_name,
    customer_email,
    customer_phone,
    delivery_address,
    product_names,
    product_prices,
    product_quantities,
    total_amount,
    status
)
VALUES
"""

    sql += ",\n".join(rows)
    sql += ";\n"

    OUTPUT_FILE.write_text(sql, encoding="utf-8")


if __name__ == "__main__":
    main()