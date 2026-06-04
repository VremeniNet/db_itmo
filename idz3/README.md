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

## Часть 2. Реплицированная таблица

Создана база данных `idz3` и таблица `events` на всех узлах кластера `idz3_cluster`.

DDL находится в файле:

```text
sql/01_create_table.sql
```

Таблица создана на движке `ReplicatedMergeTree`:

```sql
CREATE TABLE idz3.events ON CLUSTER idz3_cluster (
    event_time DateTime,
    event_type LowCardinality(String),
    user_id    UInt64,
    payload    String
)
ENGINE = ReplicatedMergeTree(
    '/clickhouse/tables/{shard}/events',
    '{replica}'
)
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_type, event_time);
```

Путь `/clickhouse/tables/{shard}/events` используется в ClickHouse Keeper для хранения журнала репликации.

Макрос `{shard}` одинаковый для всех трёх реплик и равен `shard1`.

Макрос `{replica}` отличается на каждой ноде:

- `ch1`;
- `ch2`;
- `ch3`.

После выполнения DDL таблица `events` появилась на всех трёх узлах ClickHouse.

Проверка выполнялась командами:

```powershell
docker exec -it idz3-ch1 clickhouse-client --query "SHOW TABLES FROM idz3;"
docker exec -it idz3-ch2 clickhouse-client --query "SHOW TABLES FROM idz3;"
docker exec -it idz3-ch3 clickhouse-client --query "SHOW TABLES FROM idz3;"
```

На всех трёх репликах была найдена таблица `events`.

## Часть 3. Проверка репликации

Для проверки репликации данные вставлялись только в первую реплику `ch1`.

SQL-запрос находится в файле:

```text
sql/02_insert_data.sql
```

Для генерации данных использовалась таблица-функция `numbers(120000)`:

```sql
INSERT INTO idz3.events
SELECT
    now() - toIntervalSecond(number % 86400) AS event_time,
    multiIf(
        number % 4 = 0, 'view',
        number % 4 = 1, 'click',
        number % 4 = 2, 'purchase',
        'logout'
    ) AS event_type,
    toUInt64(number % 10000) AS user_id,
    concat('payload_', toString(number)) AS payload
FROM numbers(120000);
```

После вставки было проверено количество строк на каждой реплике:

```powershell
docker exec -it idz3-ch1 clickhouse-client --query "SELECT hostName(), count() FROM idz3.events;"
docker exec -it idz3-ch2 clickhouse-client --query "SELECT hostName(), count() FROM idz3.events;"
docker exec -it idz3-ch3 clickhouse-client --query "SELECT hostName(), count() FROM idz3.events;"
```

На всех трёх репликах количество строк совпало:

| Узел | Количество строк |
|---|---:|
| `ch1` | 120000 |
| `ch2` | 120000 |
| `ch3` | 120000 |

Также был проверен статус репликации через `system.replicas`.

Результаты сохранены в файлах:

```text
checks/replicas_status_node1.txt
checks/replicas_status_node2.txt
checks/replicas_status_node3.txt
```

В нормальном состоянии у реплик:

- `total_replicas = 3`;
- `active_replicas = 3`;
- `queue_size = 0`.

Это означает, что все три реплики активны и очередь репликации пуста.

## Часть 4. Отказоустойчивость

### Эксперимент A — потеря одной реплики

В эксперименте проверялась ситуация, когда одна реплика временно недоступна.

Порядок действий:

1. Реплика `ch3` была остановлена.
2. В реплику `ch1` были вставлены новые данные.
3. Было проверено, что реплика `ch2` получила эти данные.
4. После этого `ch3` была запущена обратно.
5. Было проверено, что `ch3` догнала остальные реплики.

Для эксперимента использовался скрипт:

```text
scripts/experiment_a.py
```

В ходе эксперимента было вставлено `1 000 000` новых строк с типом события `experiment_a`.

Когда `ch3` была остановлена, данные были доступны на `ch1` и `ch2`:

| Узел | total_rows | experiment_a_rows |
|---|---:|---:|
| `ch1` | 1520000 | 1400000 |
| `ch2` | 1520000 | 1400000 |

После запуска `ch3` реплика догнала остальные узлы:

| Узел | total_rows | experiment_a_rows |
|---|---:|---:|
| `ch1` | 1520000 | 1400000 |
| `ch2` | 1520000 | 1400000 |
| `ch3` | 1520000 | 1400000 |

Финальный статус репликации на `ch3`:

| Поле | Значение |
|---|---:|
| `total_replicas` | 3 |
| `active_replicas` | 3 |
| `queue_size` | 0 |
| `inserts_in_queue` | 0 |
| `merges_in_queue` | 0 |

Это означает, что после восстановления `ch3` все три реплики снова стали активны, а очередь репликации стала пустой.

Вывод эксперимента сохранён в файле:

```text
checks/experiment_a.txt
```

Вывод `system.replication_queue` сохранён в файле:

```text
checks/replication_queue.txt
```

В момент проверки очередь уже была пустой. Это означает, что реплика `ch3` успела быстро получить недостающие данные после запуска.

### Эксперимент B — потеря Keeper-узла

В эксперименте проверялась работа кластера при потере узлов ClickHouse Keeper.

Порядок действий:

1. Все три Keeper-узла были запущены.
2. Был остановлен `keeper1`.
3. Проверено, что кворум остался жив: работали `keeper2` и `keeper3`.
4. В таблицу `events` были вставлены новые данные.
5. Был остановлен `keeper2`, после чего кворум был потерян.
6. Выполнена попытка вставки новых данных без кворума.
7. Проверено, что чтение локальных данных через `SELECT` всё ещё работает.
8. `keeper1` и `keeper2` были запущены обратно.

Для эксперимента использовался скрипт:

```text
scripts/experiment_b.py
```

Начальное состояние Keeper:

| Узел | Состояние |
|---|---|
| `keeper1` | follower |
| `keeper2` | follower |
| `keeper3` | leader |

После остановки `keeper1` кворум сохранился, потому что из трёх Keeper-узлов работали два.  
Вставка данных при одном остановленном Keeper прошла успешно.

После вставки строки с типом события `experiment_b_one_keeper_down` появились на всех трёх ClickHouse-репликах:

| Узел | total_rows | experiment_b_one_keeper_down |
|---|---:|---:|
| `ch1` | 1521000 | 1000 |
| `ch2` | 1521000 | 1000 |
| `ch3` | 1521000 | 1000 |

После остановки второго Keeper-узла кворум был потерян.  
Попытка вставки новых данных завершилась ошибкой по таймауту:

```text
TIMEOUT after 40 seconds
```

При этом чтение локальных данных продолжило работать:

| Узел | total_rows | experiment_b_one_keeper_down | experiment_b_no_quorum |
|---|---:|---:|---:|
| `ch1` | 1521000 | 1000 | 0 |

После восстановления `keeper1` и `keeper2` кворум снова стал рабочим.  
Финальное состояние репликации:

| Поле | Значение |
|---|---:|
| `total_replicas` | 3 |
| `active_replicas` | 3 |
| `queue_size` | 0 |
| `inserts_in_queue` | 0 |
| `merges_in_queue` | 0 |

Вывод эксперимента сохранён в файле:

```text
checks/experiment_b.txt
```

Вывод: при потере одного Keeper-узла кластер продолжает работать, потому что остаётся большинство узлов. При потере двух Keeper-узлов кворум пропадает, поэтому новые записи в реплицированную таблицу не проходят. При этом чтение уже имеющихся локальных данных остаётся доступным.