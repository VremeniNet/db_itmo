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