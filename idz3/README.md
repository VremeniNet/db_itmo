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

```

## Часть 1. Топология кластера

Кластер развёрнут через Docker Compose.

Используются 3 узла ClickHouse:

- `ch1`;
- `ch2`;
- `ch3`.

Также используются 3 узла ClickHouse Keeper:

- `keeper1`;
- `keeper2`;
- `keeper3`.

Keeper развёрнут отдельными контейнерами, а не совмещён с ClickHouse-узлами.  
Так топология получается более явной: отдельно видны узлы хранения данных и отдельно узлы координации репликации.

В `remote_servers` настроен кластер `idz3_cluster`:

- 1 шард;
- 3 реплики.

Для каждой ClickHouse-ноды заданы макросы:

- `cluster`;
- `shard`;
- `replica`.

Эти макросы будут использоваться при создании таблицы на движке `ReplicatedMergeTree`.

### Проверка ClickHouse Keeper

Для координации репликации используется кворум из трёх ClickHouse Keeper-узлов:

- `keeper1`;
- `keeper2`;
- `keeper3`.

Проверка выполнялась командами `ruok` и `mntr`.

Так как работа выполнялась на Windows, вместо `nc` использован Python-скрипт:

```text
scripts/check_keeper_health.py
````

Скрипт подключается к портам Keeper:

* `keeper1` — `127.0.0.1:9181`;
* `keeper2` — `127.0.0.1:9182`;
* `keeper3` — `127.0.0.1:9183`.

Команда `ruok` проверяет, что Keeper-узел жив.
Команда `mntr` выводит состояние узла и роль в кворуме.

Результат проверки сохранён в файле:

```text
checks/keeper_health.txt
```

В результате проверки все три узла ответили на `ruok`, а в выводе `mntr` видны роли узлов Keeper.