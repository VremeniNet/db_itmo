# Групповая работа 2. Multi-DB Pipeline

## Информация о студенте

**Выполнил:** Желанов Даниил
**Группа:** P4150
**Дисциплина:** Взаимодействие с базами данных


## Цель работы

Построить воспроизводимый конвейер данных для e-commerce платформы, в котором каждая СУБД решает отдельную задачу:

* PostgreSQL используется как транзакционное OLTP-ядро;
* ClickHouse используется для аналитики и агрегаций;
* ManticoreSearch используется для полнотекстового поиска по отзывам;
* Python ETL синхронизирует данные между системами;
* Grafana отображает состояние баз данных и конвейера.

## Выбранный вариант реализации

Для синхронизации используется batch ETL на Python.


## Архитектура

```text
                         PostgreSQL
                      OLTP и master data
                              |
                     Python batch ETL
                     /               \
                    v                 v
        ClickHouse 2x2           ManticoreSearch
        OLAP и аналитика         поиск по отзывам
                    \                 /
                     \               /
                            Grafana
```

ClickHouse-кластер включает:

* 2 шарда;
* 2 реплики в каждом шарде;
* 3 узла ClickHouse Keeper.

## Структура проекта

```text
group2/
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── config/
│   ├── postgresql/
│   │   └── postgresql.conf
│   ├── clickhouse/
│   │   ├── cluster.xml
│   │   ├── macros.xml
│   │   └── users.xml
│   ├── keeper/
│   │   └── keeper.xml
│   └── manticore/
│       └── manticore.conf
├── sql/
│   ├── pg/
│   │   ├── 01_schema.sql
│   │   ├── 02_seed_data.sql
│   │   └── 03_oltp_queries.sql
│   ├── ch/
│   │   ├── 01_tables.sql
│   │   ├── 02_mv.sql
│   │   └── 03_analytics.sql
│   └── manticore/
│       ├── 01_create_index.sql
│       └── 02_search_queries.sql
├── etl/
│   ├── pg_to_ch.py
│   ├── pg_to_manticore.py
│   └── requirements.txt
├── scripts/
│   ├── generate_data.py
│   ├── demo_scenario.py
│   ├── run_tests.py
│   └── run_comparison.py
├── monitoring/
│   ├── dashboards/
│   │   └── multi_db.json
│   └── provisioning/
│       ├── datasources/
│       │   └── datasources.yml
│       └── dashboards/
│           └── dashboards.yml
└── checks/
    ├── infrastructure.txt
    ├── pg_oltp.txt
    ├── ch_analytics.txt
    ├── manticore_search.txt
    ├── etl_sync.txt
    ├── comparison_table.txt
    ├── demo_output.txt
    └── monitoring_status.txt
```

## Этапы выполнения

1. Развернуть все сервисы через Docker Compose.
2. Создать нормализованную схему PostgreSQL.
3. Сгенерировать 500 000 заказов и 200 000 отзывов.
4. Проверить OLTP-операции.
5. Создать ClickHouse-кластер 2x2 и аналитические таблицы.
6. Реализовать PostgreSQL → ClickHouse ETL.
7. Создать RT-индекс ManticoreSearch.
8. Реализовать PostgreSQL → ManticoreSearch ETL.
9. Выполнить полнотекстовый и фасетный поиск.
10. Реализовать end-to-end demo-сценарий.
11. Добавить Grafana provisioning.
12. Выполнить реальные сравнительные замеры.

## Часть 1. Инфраструктура

Вся инфраструктура запускается через Docker Compose.

Обязательные сервисы:

| Сервис      | Назначение                              |
| ----------- | --------------------------------------- |
| `postgres`  | OLTP-ядро e-commerce платформы          |
| `ch-s1-r1`  | Первая реплика первого ClickHouse-шарда |
| `ch-s1-r2`  | Вторая реплика первого ClickHouse-шарда |
| `ch-s2-r1`  | Первая реплика второго ClickHouse-шарда |
| `ch-s2-r2`  | Вторая реплика второго ClickHouse-шарда |
| `keeper1`   | Первый узел ClickHouse Keeper           |
| `keeper2`   | Второй узел ClickHouse Keeper           |
| `keeper3`   | Третий узел ClickHouse Keeper           |
| `manticore` | Полнотекстовый поиск по отзывам         |
| `grafana`   | Аналитический и мониторинговый дашборд  |

Всего используется 10 сервисов.

ClickHouse-кластер называется:

```text
cluster_2x2
```

Он содержит два шарда и две реплики в каждом шарде.

Для ClickHouse-узлов используется единый шаблон конфигурации. Значения шарда и реплики передаются через переменные окружения:

```text
CLICKHOUSE_SHARD
CLICKHOUSE_REPLICA
CLICKHOUSE_HOST
```

Для трёх Keeper также используется единый файл конфигурации. Уникальный идентификатор передаётся через:

```text
KEEPER_SERVER_ID
```

Основные внешние порты:

| Компонент                    |  Порт |
| ---------------------------- | ----: |
| PostgreSQL                   | 55432 |
| Manticore MySQL protocol     | 19306 |
| Manticore HTTP API           | 19308 |
| Grafana                      | 33005 |
| ClickHouse `ch-s1-r1` HTTP   | 28411 |
| ClickHouse `ch-s1-r1` Native | 29411 |

Для управления проектом используется Makefile:

```text
make up
make down
make status
make logs
make etl
make demo
make test
```

Начальная автоматизированная проверка выполняется скриптом:

```text
scripts/run_tests.py
```

Результат сохраняется в:

```text
checks/infrastructure.txt
```
