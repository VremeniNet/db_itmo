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