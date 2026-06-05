# ИДЗ-4. Шардирование в ClickHouse

## Информация о студенте

**Выполнил:** Желанов Даниил
**Группа:** P4150
**Дисциплина:** Взаимодействие с базами данных
**СУБД:** ClickHouse

## Цель работы

Развернуть шардированный кластер ClickHouse, настроить локальные и распределённые таблицы, проверить распределение данных по шардам и выполнить запросы через `Distributed`-движок.

## Структура

```text
idz4/
├── README.md
├── docker-compose.yml
├── config/
│   ├── keeper/
│   │   ├── keeper1.xml
│   │   ├── keeper2.xml
│   │   └── keeper3.xml
│   └── clickhouse/
│       ├── cluster.xml
│       ├── s1r1_macros.xml
│       ├── s1r2_macros.xml
│       ├── s2r1_macros.xml
│       └── s2r2_macros.xml
├── sql/
│   ├── 01_create_local.sql
│   ├── 02_create_distributed.sql
│   ├── 03_user_dict.sql
│   └── 04_queries.sql
├── scripts/
│   └── generate_clickstream.py
└── checks/
    ├── cluster_info.txt
    ├── data_distribution.txt
    ├── distributed_queries.txt
    └── reshard_demo.txt
```

## Часть 1. Кластер 2x2

Кластер развёрнут через Docker Compose.

Используются 4 узла ClickHouse:

- `ch-s1-r1` — шард 1, реплика 1;
- `ch-s1-r2` — шард 1, реплика 2;
- `ch-s2-r1` — шард 2, реплика 1;
- `ch-s2-r2` — шард 2, реплика 2.

Также используются 3 узла ClickHouse Keeper:

- `keeper1`;
- `keeper2`;
- `keeper3`.

Keeper нужен для координации репликации таблиц `ReplicatedMergeTree`.

В конфигурации `remote_servers` описан кластер `cluster_2x2`:

- 2 шарда;
- по 2 реплики в каждом шарде.

Для каждого ClickHouse-узла заданы макросы:

- `{shard}`;
- `{replica}`;
- `{cluster}`.

Макросы используются при создании реплицированных таблиц, чтобы каждая реплика имела своё имя, а таблицы одного шарда использовали общий путь в ClickHouse Keeper.

Проверка кластера выполнялась запросом:

```sql
SELECT
    cluster,
    shard_num,
    replica_num,
    host_name,
    port
FROM system.clusters
WHERE cluster = 'cluster_2x2'
ORDER BY
    shard_num,
    replica_num;
```

Результат сохранён в файле:

```text
checks/cluster_info.txt
```

Результат проверки:

| cluster | shard_num | replica_num | host_name | port |
|---|---:|---:|---|---:|
| cluster_2x2 | 1 | 1 | ch-s1-r1 | 9000 |
| cluster_2x2 | 1 | 2 | ch-s1-r2 | 9000 |
| cluster_2x2 | 2 | 1 | ch-s2-r1 | 9000 |
| cluster_2x2 | 2 | 2 | ch-s2-r2 | 9000 |