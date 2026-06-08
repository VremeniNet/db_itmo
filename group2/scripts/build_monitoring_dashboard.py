import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]

DASHBOARD_FILE = (
    ROOT_DIR
    / "monitoring"
    / "dashboards"
    / "multi_db.json"
)


POSTGRES_DATASOURCE = {
    "type": "postgres",
    "uid": "postgresql",
}

CLICKHOUSE_DATASOURCE = {
    "type": "grafana-clickhouse-datasource",
    "uid": "clickhouse",
}


def postgres_target(
    sql: str,
    ref_id: str = "A",
) -> dict[str, Any]:
    return {
        "datasource": POSTGRES_DATASOURCE,
        "editorMode": "code",
        "format": "table",
        "rawQuery": True,
        "rawSql": sql.strip(),
        "refId": ref_id,
    }


def clickhouse_target(
    sql: str,
    ref_id: str = "A",
) -> dict[str, Any]:
    return {
        "datasource": CLICKHOUSE_DATASOURCE,
        "editorType": "sql",
        "format": 1,
        "queryType": "table",
        "rawSql": sql.strip(),
        "refId": ref_id,
    }


def stat_panel(
    panel_id: int,
    title: str,
    datasource: dict[str, str],
    target: dict[str, Any],
    x: int,
    y: int,
    unit: str = "short",
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "type": "stat",
        "datasource": datasource,
        "gridPos": {
            "h": 6,
            "w": 8,
            "x": x,
            "y": y,
        },
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {
                            "color": "green",
                            "value": None,
                        }
                    ],
                },
            },
            "overrides": [],
        },
        "options": {
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "center",
            "orientation": "horizontal",
            "reduceOptions": {
                "calcs": [
                    "lastNotNull"
                ],
                "fields": "",
                "values": False,
            },
            "showPercentChange": False,
            "textMode": "auto",
            "wideLayout": True,
        },
        "targets": [
            target
        ],
    }


def table_panel(
    panel_id: int,
    title: str,
    datasource: dict[str, str],
    target: dict[str, Any],
    x: int,
    y: int,
    width: int = 12,
    height: int = 8,
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "type": "table",
        "datasource": datasource,
        "gridPos": {
            "h": height,
            "w": width,
            "x": x,
            "y": y,
        },
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "align": "auto",
                    "cellOptions": {
                        "type": "auto",
                    },
                    "inspect": False,
                },
                "mappings": [],
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {
                            "color": "green",
                            "value": None,
                        }
                    ],
                },
            },
            "overrides": [],
        },
        "options": {
            "cellHeight": "sm",
            "footer": {
                "countRows": False,
                "enablePagination": False,
                "fields": "",
                "reducer": [
                    "sum"
                ],
                "show": False,
            },
            "showHeader": True,
            "sortBy": [],
        },
        "targets": [
            target
        ],
    }


def main() -> None:
    panels: list[dict[str, Any]] = []

    panels.append(
        stat_panel(
            panel_id=1,
            title="PostgreSQL active connections",
            datasource=POSTGRES_DATASOURCE,
            target=postgres_target(
                """
SELECT
    count(*) AS value
FROM pg_stat_activity
WHERE datname = current_database()
"""
            ),
            x=0,
            y=0,
        )
    )

    panels.append(
        stat_panel(
            panel_id=2,
            title="PostgreSQL transactions per second",
            datasource=POSTGRES_DATASOURCE,
            target=postgres_target(
                """
SELECT
    pg_tps AS value
FROM monitoring.pipeline_metrics
ORDER BY collected_at DESC
LIMIT 1
"""
            ),
            x=8,
            y=0,
            unit="ops",
        )
    )

    panels.append(
        stat_panel(
            panel_id=3,
            title="ClickHouse analytics rows",
            datasource=CLICKHOUSE_DATASOURCE,
            target=clickhouse_target(
                """
SELECT
    count() AS value
FROM ecommerce.orders_analytics_distributed
"""
            ),
            x=16,
            y=0,
        )
    )

    panels.append(
        stat_panel(
            panel_id=4,
            title="ClickHouse queries per second",
            datasource=POSTGRES_DATASOURCE,
            target=postgres_target(
                """
SELECT
    ch_qps AS value
FROM monitoring.pipeline_metrics
ORDER BY collected_at DESC
LIMIT 1
"""
            ),
            x=0,
            y=6,
            unit="qps",
        )
    )

    panels.append(
        stat_panel(
            panel_id=5,
            title="ManticoreSearch documents",
            datasource=POSTGRES_DATASOURCE,
            target=postgres_target(
                """
SELECT
    manticore_documents AS value
FROM monitoring.pipeline_metrics
ORDER BY collected_at DESC
LIMIT 1
"""
            ),
            x=8,
            y=6,
        )
    )

    panels.append(
        stat_panel(
            panel_id=6,
            title="ManticoreSearch search time",
            datasource=POSTGRES_DATASOURCE,
            target=postgres_target(
                """
SELECT
    manticore_search_ms AS value
FROM monitoring.pipeline_metrics
ORDER BY collected_at DESC
LIMIT 1
"""
            ),
            x=16,
            y=6,
            unit="ms",
        )
    )

    panels.append(
        table_panel(
            panel_id=7,
            title="PostgreSQL table sizes",
            datasource=POSTGRES_DATASOURCE,
            target=postgres_target(
                """
SELECT
    relname AS table_name,
    pg_size_pretty(
        pg_total_relation_size(relid)
    ) AS total_size,
    pg_total_relation_size(relid)
        AS total_size_bytes
FROM pg_catalog.pg_statio_user_tables
ORDER BY total_size_bytes DESC
LIMIT 10
"""
            ),
            x=0,
            y=12,
            width=12,
            height=9,
        )
    )

    panels.append(
        table_panel(
            panel_id=8,
            title="ClickHouse replication status",
            datasource=CLICKHOUSE_DATASOURCE,
            target=clickhouse_target(
                """
SELECT
    hostName() AS node,
    table,
    replica_name,
    total_replicas,
    active_replicas,
    queue_size,
    absolute_delay
FROM clusterAllReplicas(
    'cluster_2x2',
    system.replicas
)
WHERE database = 'ecommerce'
ORDER BY
    node,
    table
"""
            ),
            x=12,
            y=12,
            width=12,
            height=9,
        )
    )

    panels.append(
        table_panel(
            panel_id=9,
            title="Pipeline synchronization status",
            datasource=POSTGRES_DATASOURCE,
            target=postgres_target(
                """
SELECT
    last_sync,
    orders_processed,
    reviews_processed,
    ch_rows,
    manticore_documents
FROM monitoring.pipeline_metrics
ORDER BY collected_at DESC
LIMIT 1
"""
            ),
            x=0,
            y=21,
            width=24,
            height=7,
        )
    )

    dashboard = {
        "annotations": {
            "list": []
        },
        "description": (
            "PostgreSQL, ClickHouse, ManticoreSearch "
            "and ETL pipeline monitoring."
        ),
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": panels,
        "refresh": "10s",
        "schemaVersion": 39,
        "tags": [
            "postgresql",
            "clickhouse",
            "manticore",
            "pipeline",
        ],
        "templating": {
            "list": []
        },
        "time": {
            "from": "now-1h",
            "to": "now",
        },
        "timepicker": {},
        "timezone": "browser",
        "title": "Multi-DB Pipeline",
        "uid": "multi-db-pipeline",
        "version": 2,
        "weekStart": "",
    }

    DASHBOARD_FILE.write_text(
        json.dumps(
            dashboard,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Dashboard saved to: {DASHBOARD_FILE}"
    )
    print(
        f"Panels created: {len(panels)}"
    )


if __name__ == "__main__":
    main()