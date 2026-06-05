# ИДЗ-5. ManticoreSearch: полнотекстовый поиск и NoSQL-подход

## Информация о студенте

**Выполнил:** Желанов Даниил
**Группа:** P4150
**Дисциплина:** Взаимодействие с базами данных
**СУБД:** ManticoreSearch

## Цель работы

Развернуть ManticoreSearch, создать real-time индекс для каталога товаров, загрузить тестовые данные, выполнить полнотекстовый поиск, фасетный поиск и сравнить подход поискового движка с PostgreSQL.

## Структура

```text
idz5/
├── README.md
├── docker-compose.yml
├── config/
│   └── manticore.conf
├── sql/
│   ├── 01_create_index.sql
│   ├── 02_search_queries.sql
│   ├── 03_facets.sql
│   ├── 04_update_delete.sql
│   └── 05_pg_comparison.sql
├── scripts/
│   └── load_products.py
└── checks/
    ├── connectivity.txt
    ├── basic_search.txt
    ├── phrase_search.txt
    ├── proximity_search.txt
    ├── filtered_search.txt
    ├── json_search.txt
    ├── facets.txt
    ├── update_delete.txt
    └── pg_vs_manticore.txt
```
