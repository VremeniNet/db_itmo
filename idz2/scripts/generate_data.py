import argparse
import subprocess
from pathlib import Path


CONTAINER_NAME = "idz2-clickhouse"


def run_command(command: list[str], input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def build_sql(rows_count: int) -> str:
    return f"""
TRUNCATE TABLE idz2.orders_flat;
TRUNCATE TABLE idz2.monthly_sales;

INSERT INTO idz2.orders_flat
WITH
    number AS row_number,
    intDiv(row_number, 3) + 1 AS order_num,

    ['Федорова Ольга Николаевна',
     'Иванов Иван Иванович',
     'Кузнецов Алексей Олегович',
     'Морозова Елена Павловна',
     'Новиков Артем Максимович',
     'Васильев Дмитрий Игоревич',
     'Сидорова Анна Сергеевна',
     'Смирнова Мария Андреевна',
     'Соколов Кирилл Денисович',
     'Петров Петр Петрович'] AS customer_names,

    ['fedorova@example.com',
     'ivanov@example.com',
     'kuznetsov@example.com',
     'morozova@example.com',
     'novikov@example.com',
     'vasiliev@example.com',
     'sidorova@example.com',
     'smirnova@example.com',
     'sokolov@example.com',
     'petrov@example.com'] AS customer_emails,

    ['Санкт-Петербург',
     'Москва',
     'Казань',
     'Новосибирск',
     'Екатеринбург',
     'Нижний Новгород',
     'Пермь',
     'Самара'] AS regions,

    ['USB-хаб',
     'Веб-камера',
     'Внешний SSD',
     'Кабель HDMI',
     'Клавиатура',
     'Коврик',
     'Монитор',
     'Мышь',
     'Наушники',
     'Ноутбук'] AS product_names,

    ['Аксессуары',
     'Периферия',
     'Компьютерная техника',
     'Аксессуары',
     'Периферия',
     'Аксессуары',
     'Компьютерная техника',
     'Периферия',
     'Периферия',
     'Компьютерная техника'] AS categories,

    [2500, 4500, 12000, 900, 3500, 500, 22000, 1500, 6000, 85000] AS prices,

    ['new', 'processing', 'shipped', 'delivered', 'cancelled'] AS statuses,

    toUInt64((order_num % 10) + 1) AS customer_idx,
    toUInt64((row_number % 10) + 1) AS product_idx,
    toUInt64((order_num % 8) + 1) AS region_idx,
    toUInt64((order_num % 5) + 1) AS status_idx,

    toDate('2024-01-01') + toIntervalDay(toUInt32(order_num % 365)) AS generated_order_date,
    toUInt32((row_number % 3) + 1) AS generated_quantity,
    arrayElement(prices, product_idx) AS generated_price
SELECT
    generated_order_date AS order_date,
    toDateTime(generated_order_date) + toIntervalSecond(toUInt32((order_num * 37) % 86400)) AS order_datetime,
    toUInt64(order_num) AS order_id,
    toUInt64(customer_idx) AS customer_id,
    arrayElement(customer_names, customer_idx) AS customer_name,
    arrayElement(customer_emails, customer_idx) AS customer_email,
    arrayElement(regions, region_idx) AS region,
    toUInt64(product_idx) AS product_id,
    arrayElement(product_names, product_idx) AS product_name,
    arrayElement(categories, product_idx) AS category,
    generated_quantity AS quantity,
    toDecimal64(generated_price, 2) AS price,
    toDecimal64(generated_price * generated_quantity, 2) AS line_total,
    arrayElement(statuses, status_idx) AS order_status
FROM numbers({rows_count});

INSERT INTO idz2.monthly_sales
SELECT
    toStartOfMonth(order_date) AS month,
    category,
    region,
    sum(toUInt64(quantity)) AS total_qty,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
GROUP BY
    month,
    category,
    region;

SELECT
    'orders_flat' AS table_name,
    count() AS rows_count
FROM idz2.orders_flat
UNION ALL
SELECT
    'monthly_sales' AS table_name,
    count() AS rows_count
FROM idz2.monthly_sales;

SELECT
    min(order_date) AS min_order_date,
    max(order_date) AS max_order_date,
    count() AS rows_count
FROM idz2.orders_flat;
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parents[1]
    checks_dir = project_dir / "checks"
    checks_dir.mkdir(exist_ok=True)

    output_file = checks_dir / "load_data.txt"

    start_result = run_command(["docker", "start", CONTAINER_NAME])

    sql = build_sql(args.rows)

    result = run_command(
        [
            "docker",
            "exec",
            "-i",
            CONTAINER_NAME,
            "clickhouse-client",
            "--multiquery",
        ],
        input_text=sql,
    )

    output = []
    output.append("ClickHouse data generation")
    output.append("")
    output.append(f"Rows requested: {args.rows}")
    output.append("")
    output.append("docker start output:")
    output.append(start_result.stdout.strip())
    output.append("")
    output.append("clickhouse-client output:")
    output.append(result.stdout.strip())
    output.append("")

    output_file.write_text("\n".join(output), encoding="utf-8")

    print("\n".join(output))

    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()