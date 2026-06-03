# ИДЗ-2. ClickHouse: колоночное хранилище, движки и OLAP-аналитика

## Информация о студенте

**Выполнил:** Желанов Даниил  
**Группа:** P4150  
**Дисциплина:** Взаимодействие с базами данных  
**СУБД:** ClickHouse  

## Цель работы

Развернуть ClickHouse, спроектировать схему под аналитическую нагрузку, загрузить данные интернет-магазина из ИДЗ-1 в денормализованном виде и выполнить OLAP-запросы.

## Структура

```text
idz2/
├── README.md
├── sql/
│   ├── 01_create_db.sql
│   ├── 02_orders_flat.sql
│   ├── 03_orders_ttl.sql
│   ├── 04_monthly_sales.sql
│   ├── 05_queries.sql
│   └── 06_system_tables.sql
├── scripts/
│   ├── generate_data.py
│   └── pg_to_ch.py
├── config/
│   ├── users.xml
│   └── config.d/
│       └── listen.xml
└── checks/
    ├── top10_products.txt
    ├── monthly_sales.txt
    ├── p99_order_value.txt
    ├── summing_vs_raw.txt
    ├── ttl_demo.txt
    ├── compression_stats.txt
    └── pg_vs_ch_comparison.txt
```

## Часть 1. Установка и начальная настройка

ClickHouse запущен в Docker-контейнере `idz2-clickhouse`.

Добавлены конфигурационные файлы:

- `config/config.d/listen.xml` — настройка прослушивания на `0.0.0.0`;
- `config/users.xml` — профиль `readonly` и пользователь `analyst`.

Для пользователя `analyst` создан профиль только для чтения:

```xml
<readonly>1</readonly>
```

Проверено подключение от пользователей:

* `default`;
* `analyst`.

Также проверено, что пользователь `analyst` не может выполнять команды изменения схемы, например `CREATE DATABASE`.

Результаты проверки сохранены в файле `checks/connection_check.txt`.

---

## Часть 2. Проектирование схемы

В ClickHouse данные хранятся в денормализованном виде.  
В отличие от PostgreSQL, где в ИДЗ-1 схема была приведена к 3NF, здесь основная таблица будет плоской.

Создана таблица `orders_flat` на движке `MergeTree`.

В этой таблице одна строка соответствует одной позиции заказа: данные заказа, клиента, товара, категории и суммы хранятся вместе.

Для строковых полей с небольшим количеством различных значений используется `LowCardinality(String)`:

- `customer_email`;
- `region`;
- `category`;
- `order_status`.

Это позволяет ClickHouse эффективнее хранить повторяющиеся строковые значения.

Ключ сортировки:

```sql
ORDER BY (category, toStartOfHour(order_datetime), order_status)
```

Такой ключ выбран, потому что аналитические запросы часто используют категорию, время заказа и статус.

### Таблица `orders_ttl`

Создана таблица `orders_ttl` на движке `MergeTree` с TTL.

По структуре она совпадает с `orders_flat`, но дополнительно содержит правило:

```sql
TTL order_date + INTERVAL 90 DAY DELETE
```

Это означает, что строки старше 90 дней могут быть удалены ClickHouse во время merge-операций.

Такая таблица нужна для данных с ограниченным сроком хранения. Например, если старые события или заказы больше не нужны в горячем хранилище, их можно автоматически удалять через TTL.


### Таблица `monthly_sales`

Создана таблица `monthly_sales` на движке `SummingMergeTree`.

Эта таблица нужна для хранения заранее рассчитанных агрегатов по продажам:

- месяц;
- категория;
- регион;
- суммарное количество товаров;
- суммарная выручка.

```sql
CREATE TABLE idz2.monthly_sales (
    month         Date,
    category      LowCardinality(String),
    region        LowCardinality(String),
    total_qty     UInt64,
    total_revenue Decimal(18, 2)
)
ENGINE = SummingMergeTree((total_qty, total_revenue))
PARTITION BY toYYYYMM(month)
ORDER BY (month, category, region);
```

`SummingMergeTree` выбран потому, что таблица хранит агрегированные данные.
Если строки имеют одинаковые значения `month`, `category` и `region`, то числовые поля `total_qty` и `total_revenue` могут суммироваться при merge-операциях.

Такая таблица нужна для аналитики: вместо пересчёта продаж по сырой таблице `orders_flat` можно читать уже подготовленные агрегаты.

---

## Часть 3. Загрузка данных

Данные для ClickHouse генерируются скриптом:

```text
scripts/generate_data.py
````

Скрипт заполняет таблицу `orders_flat` с помощью запроса:

```sql
INSERT INTO idz2.orders_flat
SELECT ...
FROM numbers(1000000);
```

В результате создаётся 1 000 000 строк.
Одна строка соответствует одной позиции заказа.

После загрузки `orders_flat` скрипт также заполняет агрегатную таблицу `monthly_sales`:

```sql
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
```

Результат выполнения сохранён в файле:

```text
checks/load_data.txt
```

В отличие от PostgreSQL из ИДЗ-1, данные здесь хранятся в плоском виде: в одной строке находятся данные заказа, клиента, товара, категории и суммы позиции. Это удобно для OLAP-запросов, потому что не нужно выполнять `JOIN` нескольких таблиц во время аналитического запроса.

---

## Часть 4. Бизнес-запросы

Для ClickHouse были выполнены аналитические запросы к таблице `orders_flat`.

SQL-запросы находятся в файле:

```text
sql/05_queries.sql
```

Результаты выполнения сохранены в файлах:

```text
checks/top10_products.txt
checks/monthly_sales.txt
checks/p99_order_value.txt
checks/search_customer.txt
checks/summing_vs_raw.txt
```

### 1. Топ-10 товаров по выручке

```sql
SELECT
    product_id,
    product_name,
    category,
    sum(quantity) AS total_qty,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
GROUP BY
    product_id,
    product_name,
    category
ORDER BY total_revenue DESC
LIMIT 10;
```

Результат:

| product_id | product_name | category             | total_qty | total_revenue |
| ---------: | ------------ | -------------------- | --------: | ------------: |
|         10 | Ноутбук      | Компьютерная техника |    199999 |   16999915000 |
|          7 | Монитор      | Компьютерная техника |    199999 |    4399978000 |
|          3 | Внешний SSD  | Компьютерная техника |    200001 |    2400012000 |
|          9 | Наушники     | Периферия            |    200001 |    1200006000 |
|          2 | Веб-камера   | Периферия            |    200000 |     900000000 |
|          5 | Клавиатура   | Периферия            |    200000 |     700000000 |
|          1 | USB-хаб      | Аксессуары           |    199999 |     499997500 |
|          8 | Мышь         | Периферия            |    200000 |     300000000 |
|          4 | Кабель HDMI  | Аксессуары           |    199999 |     179999100 |
|          6 | Коврик       | Аксессуары           |    200001 |     100000500 |

Время выполнения:

```text
0.691 sec
```

### 2. Ежемесячная динамика продаж по категориям

```sql
SELECT
    toStartOfMonth(order_date) AS month,
    category,
    sum(quantity) AS total_qty,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
GROUP BY
    month,
    category
ORDER BY
    month,
    category;
```

Пример результата:

| month      | category             | total_qty | total_revenue |
| ---------- | -------------------- | --------: | ------------: |
| 2024-01-01 | Аксессуары           |     50270 |      64985400 |
| 2024-01-01 | Компьютерная техника |     51181 |    2079552000 |
| 2024-01-01 | Периферия            |     68547 |     265960500 |
| 2024-02-01 | Аксессуары           |     48442 |      63340200 |
| 2024-02-01 | Компьютерная техника |     47528 |    1835769000 |
| 2024-02-01 | Периферия            |     63066 |     244038000 |

Время выполнения:

```text
0.084 sec
```

### 3. Процентили p95 и p99 стоимости заказа

Так как в `orders_flat` одна строка соответствует позиции заказа, сначала считается сумма каждого заказа, а потом по этим суммам считаются процентили.

```sql
WITH order_totals AS (
    SELECT
        order_id,
        sum(toFloat64(line_total)) AS order_total
    FROM idz2.orders_flat
    GROUP BY order_id
)
SELECT
    quantileExact(0.95)(order_total) AS p95_order_value,
    quantileExact(0.99)(order_total) AS p99_order_value,
    avg(order_total) AS avg_order_value,
    count() AS orders_count
FROM order_totals;
```

Результат:

| p95_order_value | p99_order_value |   avg_order_value | orders_count |
| --------------: | --------------: | ----------------: | -----------: |
|          268500 |          268500 | 83039.55822088355 |       333334 |

Время выполнения:

```text
0.161 sec
```

### 4. Поиск клиента по подстроке email

```sql
SELECT
    customer_id,
    customer_name,
    customer_email,
    count() AS rows_count,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
WHERE positionCaseInsensitive(customer_email, 'ivanov') > 0
GROUP BY
    customer_id,
    customer_name,
    customer_email
ORDER BY rows_count DESC;
```

Результат:

| customer_id | customer_name        | customer_email                                  | rows_count | total_revenue |
| ----------: | -------------------- | ----------------------------------------------- | ---------: | ------------: |
|           2 | Иванов Иван Иванович | [ivanov@example.com](mailto:ivanov@example.com) |     100002 |    1583365000 |

Время выполнения:

```text
0.115 sec
```

### 5. Сравнение `orders_flat` и `monthly_sales`

Сначала агрегаты были посчитаны из сырой таблицы `orders_flat`:

```sql
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
    region
ORDER BY
    month,
    category,
    region
LIMIT 20;
```

Затем те же данные были получены из заранее рассчитанной таблицы `monthly_sales`:

```sql
SELECT
    month,
    category,
    region,
    sum(total_qty) AS total_qty,
    sum(total_revenue) AS total_revenue
FROM idz2.monthly_sales
GROUP BY
    month,
    category,
    region
ORDER BY
    month,
    category,
    region
LIMIT 20;
```

Пример результата совпадает для обоих вариантов:

| month      | category   | region          | total_qty | total_revenue |
| ---------- | ---------- | --------------- | --------: | ------------: |
| 2024-01-01 | Аксессуары | Екатеринбург    |      6856 |       7265600 |
| 2024-01-01 | Аксессуары | Казань          |      6854 |       7264200 |
| 2024-01-01 | Аксессуары | Москва          |      5715 |       8983500 |
| 2024-01-01 | Аксессуары | Нижний Новгород |      5710 |       8971000 |
| 2024-01-01 | Аксессуары | Новосибирск     |      5714 |       8984200 |

Сравнение времени выполнения:

| Источник        | Что делает                           |     Время |
| --------------- | ------------------------------------ | --------: |
| `orders_flat`   | считает агрегаты из 1 000 000 строк  | 0.213 sec |
| `monthly_sales` | читает заранее рассчитанные агрегаты | 0.014 sec |

`monthly_sales` работает быстрее, потому что данные уже агрегированы по месяцу, категории и региону. В отличие от запроса к `orders_flat`, ClickHouse не нужно заново группировать миллион строк.

---

## Часть 5. Демонстрация TTL

Для демонстрации TTL использовалась таблица `orders_ttl`.

Сначала таблица была создана без TTL, затем в неё были добавлены тестовые строки:

- 3 строки со старой датой старше 90 дней;
- 2 строки с текущей датой.

После этого для таблицы было добавлено TTL-правило:

```sql
ALTER TABLE idz2.orders_ttl
MODIFY TTL order_date + INTERVAL 90 DAY DELETE;
```

Это правило означает, что строки старше 90 дней должны удаляться во время merge-операций ClickHouse.

Чтобы применить TTL сразу, была выполнена команда:

```sql
OPTIMIZE TABLE idz2.orders_ttl FINAL;
```

Проверка количества строк:

| Этап | Количество строк |
|---|---:|
| До применения TTL | 5 |
| После применения TTL | 2 |

После применения TTL в таблице остались только актуальные строки:

| order_id | order_date | product_name | category | line_total | order_status |
|---:|---|---|---|---:|---|
| 900004 | 2026-06-03 | USB hub | Accessories | 2500 | new |
| 900005 | 2026-06-03 | Keyboard | Periphery | 3500 | new |

Вывод `system.parts` до и после применения TTL сохранён в файле:

```text
checks/ttl_demo.txt
```

TTL полезен для данных с ограниченным сроком хранения. Например, старые события, логи или временные аналитические данные можно автоматически удалять без ручного `DELETE`.