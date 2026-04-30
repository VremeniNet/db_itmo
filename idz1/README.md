# ИДЗ-1. PostgreSQL: структуры данных, нормализация и денормализация

## Информация о студенте

**Выполнил:** Желанов Даниил  
**Группа:** P4150  
**Дисциплина:** Взаимодействие с базами данных  
**СУБД:** PostgreSQL 17.4  

## Цель работы

Спроектировать реляционную базу данных в PostgreSQL, пройти путь от ненормализованной «плоской» таблицы до 3NF, затем осознанно денормализовать под конкретный сценарий чтения. Понять, когда нормализация помогает, а когда мешает.

## Структура

```text
idz1/
├── README.md
├── schema.puml
├── sql/
│   ├── 00_orders_raw.sql
│   ├── 01_to_1nf.sql
│   ├── 02_to_2nf.sql
│   ├── 03_to_3nf.sql
│   ├── 04_oltp_queries.sql
│   ├── 05_indexes.sql
│   ├── 06_denorm_mv.sql
│   └── 07_denorm_table.sql
├── scripts/
│   └── generate_data.py
└── checks/
    ├── anomalies.txt
    ├── explain_before_idx.txt
    ├── explain_after_idx.txt
    ├── mv_vs_join.txt
    └── trgm_demo.txt
```

## Часть 1. Ненормализованная таблица

Создана таблица `orders_raw`, которая имитирует выгрузку из Excel.

В таблице данные о заказе, клиенте, адресе доставки и товарах хранятся вместе.
Поля `product_names`, `product_prices` и `product_quantities` содержат списки значений через запятую, поэтому таблица не находится в 1NF.

Тестовые данные генерируются скриптом `scripts/generate_data.py`.
Скрипт создаёт 1200 строк.

### Аномалии

**Аномалия вставки.**  
Нельзя добавить товар отдельно от заказа. Например, товар Игровое кресло с ценой 18990 пришлось бы добавлять через создание фиктивного заказа.

**Аномалия обновления.**  
Данные клиента повторяются в нескольких строках. Если у клиента изменится телефон или email, нужно обновлять все его заказы. Если обновить только часть строк, появятся разные данные об одном и том же клиенте.

**Аномалия удаления.**  
Информация о товарах хранится только внутри заказов. Если удалить все заказы, где встречается товар, например USB-хаб, то информация об этом товаре исчезнет из базы.

## Часть 2. Нормализация до 3NF

### 1NF

На первом шаге составные поля `product_names`, `product_prices` и `product_quantities` были разбиты на отдельные строки.

Созданы таблицы:

- `orders_1nf` — данные заказа;
- `order_items_1nf` — товары внутри заказа.

Проверка количества строк:

```sql
SELECT 'orders_1nf' AS table_name, COUNT(*) AS rows_count FROM orders_1nf
UNION ALL
SELECT 'order_items_1nf' AS table_name, COUNT(*) AS rows_count FROM order_items_1nf;
```

Результат:

|table_name    | rows_count |       
|-----------------|-----------|
|orders_1nf      |       1200|
|order_items_1nf |       3098|

Пример данных из `orders_1nf`:

```sql
SELECT order_id, order_date, customer_name, customer_email, customer_phone,
       delivery_address, total_amount, status
FROM orders_1nf
ORDER BY order_id
LIMIT 5;
```

| order_id | order_date | customer_name | customer_email | customer_phone | delivery_address | total_amount | status |
|---:|---|---|---|---|---|---:|---|
| 1 | 2024-08-28 | Иванов Иван Иванович | ivanov@example.com | +79990000001 | Санкт-Петербург, Литейный проспект, д. 25 | 52000 | delivered |
| 2 | 2024-08-05 | Сидорова Анна Сергеевна | sidorova@example.com | +79990000003 | Санкт-Петербург, Литейный проспект, д. 25 | 4500 | delivered |
| 3 | 2024-03-22 | Сидорова Анна Сергеевна | sidorova@example.com | +79990000003 | Новосибирск, Красный проспект, д. 31 | 8000 | processing |
| 4 | 2024-07-25 | Иванов Иван Иванович | ivanov@example.com | +79990000001 | Москва, ул. Тверская, д. 7 | 6900 | processing |
| 5 | 2024-12-21 | Федорова Ольга Николаевна | fedorova@example.com | +79990000009 | Санкт-Петербург, Московский проспект, д. 120 | 2400 | new |

Пример данных из `order_items_1nf`:

```sql
SELECT order_id, item_position, product_name, product_price, product_quantity
FROM order_items_1nf
ORDER BY order_id, item_position
LIMIT 10;
```

| order_id | item_position | product_name | product_price | product_quantity |
|---:|---:|---|---:|---:|
| 1 | 1 | Веб-камера | 4500 | 1 |
| 1 | 2 | Монитор | 22000 | 2 |
| 1 | 3 | Клавиатура | 3500 | 1 |
| 2 | 1 | Мышь | 1500 | 3 |
| 3 | 1 | USB-хаб | 2500 | 2 |
| 3 | 2 | Мышь | 1500 | 2 |
| 4 | 1 | Кабель HDMI | 900 | 1 |
| 4 | 2 | Коврик | 500 | 2 |
| 4 | 3 | USB-хаб | 2500 | 2 |
| 5 | 1 | Кабель HDMI | 900 | 1 |

Теперь одна строка в `order_items_1nf` соответствует одному товару в заказе.  
Повторяющиеся группы убраны, но данные клиента и товара пока ещё могут дублироваться. Это будет исправляться при переходе к 2NF.