# ИДЗ-3. Репликация в ClickHouse

## Информация о студенте

**Выполнил:** Желанов Даниил  
**Группа:** P4150  
**Дисциплина:** Взаимодействие с базами данных  
**СУБД:** ClickHouse  

## Цель работы

Развернуть ClickHouse-кластер с репликацией, настроить ClickHouse Keeper, создать таблицу на движке `ReplicatedMergeTree`, проверить репликацию данных между узлами и провести эксперименты с отказоустойчивостью.

## Структура

```text
idz3/
├── README.md
├── docker-compose.yml
├── config/
│   ├── keeper/
│   │   ├── keeper1.xml
│   │   ├── keeper2.xml
│   │   └── keeper3.xml
│   └── clickhouse/
│       ├── cluster.xml
│       ├── node1_macros.xml
│       ├── node2_macros.xml
│       └── node3_macros.xml
├── sql/
│   ├── 01_create_table.sql
│   └── 02_insert_data.sql
├── scripts/
│   └── generate_events.py
└── checks/
    ├── keeper_health.txt
    ├── replicas_status_node1.txt
    ├── replicas_status_node2.txt
    ├── replicas_status_node3.txt
    ├── experiment_a.txt
    ├── experiment_b.txt
    ├── experiment_c.txt
    └── replication_queue.txt