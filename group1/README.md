# Групповая работа 1. HA-кластер ClickHouse 2x2 с мониторингом и балансировкой

## Информация о студенте

**Выполнил:** Желанов Даниил
**Группа:** P4150
**Дисциплина:** Взаимодействие с базами данных

## Формат выполнения

Работа выполняется индивидуально.

Все компоненты инфраструктуры, конфигурация ClickHouse и Keeper, балансировка через Nginx, мониторинг Prometheus и Grafana, автоматизированные проверки и эксперименты с отказоустойчивостью выполняются одним студентом.

| Участник       | Зона ответственности                                                                                                              |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Желанов Даниил | ClickHouse-кластер, Keeper, Nginx, Prometheus, Grafana, генерация данных, Makefile, автоматизированные проверки и fault injection |


## Цель работы

Развернуть отказоустойчивый кластер ClickHouse с балансировщиком нагрузки, мониторингом и автоматизированными проверками.

Инфраструктура должна запускаться одной командой и включать:

* 4 узла ClickHouse: 2 шарда по 2 реплики;
* 3 узла ClickHouse Keeper;
* Nginx в роли HTTP-балансировщика;
* Prometheus для сбора метрик;
* Grafana с автоматически загружаемым дашбордом.

Всего используется 10 сервисов.

## Планируемая топология

```text
                         client
                            |
                         nginx
                            |
        +-------------------+-------------------+
        |                   |                   |
    ch-s1-r1            ch-s1-r2            ch-s2-r1
    shard 1             shard 1             shard 2
                                                |
                                            ch-s2-r2
                                            shard 2

        keeper1          keeper2          keeper3

                    prometheus + grafana
```

## Структура проекта

```text
group1/
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── config/
│   ├── clickhouse/
│   │   ├── cluster.xml
│   │   ├── prometheus.xml
│   │   ├── users.xml
│   │   └── macros.xml
│   ├── keeper/
│   │   └── keeper.xml
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── upstream.conf
│   └── prometheus/
│       └── prometheus.yml
├── monitoring/
│   ├── dashboards/
│   │   └── clickhouse.json
│   └── provisioning/
│       ├── datasources.yml
│       └── dashboards.yml
├── sql/
│   ├── 01_create_tables.sql
│   └── 02_test_queries.sql
├── scripts/
│   ├── generate_data.py
│   ├── fault_injection.py
│   └── run_tests.py
└── checks/
    ├── cluster_status.txt
    ├── data_distribution.txt
    ├── nginx_failover.txt
    ├── fault_scenarios.txt
    └── grafana_screenshots_NOT_ALLOWED.md
```
## Часть 1. Инфраструктура как код

Вся инфраструктура описана в файле:

```text
docker-compose.yml
```

Кластер состоит из 10 сервисов:

* 4 узла ClickHouse;
* 3 узла ClickHouse Keeper;
* Nginx;
* Prometheus;
* Grafana.

Для запуска используются переменные из файла `.env`. Пример настроек находится в `.env.example`.

Конфигурация шаблонизирована. В `docker-compose.yml` используются общие YAML-шаблоны:

```text
x-clickhouse-common
x-clickhouse-environment
x-keeper-common
```

Все ClickHouse-узлы используют одинаковые файлы конфигурации. Значения шарда, реплики и имени узла передаются через переменные окружения:

```text
CLICKHOUSE_SHARD
CLICKHOUSE_REPLICA
CLICKHOUSE_HOST
```

Единый файл `config/clickhouse/macros.xml` получает эти значения через `from_env`.

Для всех Keeper-узлов также используется один файл:

```text
config/keeper/keeper.xml
```

Уникальный `server_id` передаётся через переменную:

```text
KEEPER_SERVER_ID
```

Таким образом, в проекте нет четырёх копий одного ClickHouse-конфига и трёх копий одного Keeper-конфига.

Для управления инфраструктурой создан Makefile с командами:

```text
make up
make down
make status
make test
make logs
make restart
```

Команда `make test` запускает скрипт:

```text
scripts/run_tests.py
```

Скрипт проверяет:

* состояние всех 10 сервисов;
* доступность Nginx;
* выполнение ClickHouse-запроса через Nginx;
* готовность Prometheus;
* доступность Grafana.

Результат проверки сохраняется в:

```text
checks/cluster_status.txt
```
