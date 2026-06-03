SELECT
    column,
    any(type) AS type,
    formatReadableSize(sum(column_data_compressed_bytes)) AS compressed,
    formatReadableSize(sum(column_data_uncompressed_bytes)) AS uncompressed,
    round(
        sum(column_data_uncompressed_bytes) / sum(column_data_compressed_bytes),
        2
    ) AS ratio
FROM system.parts_columns
WHERE database = 'idz2'
  AND table = 'orders_flat'
  AND active
GROUP BY column
ORDER BY sum(column_data_uncompressed_bytes) DESC
FORMAT TabSeparatedWithNames;

SELECT
    'orders_flat' AS table_name,
    count() AS active_parts,
    sum(rows) AS rows,
    formatReadableSize(sum(bytes_on_disk)) AS size_on_disk
FROM system.parts
WHERE database = 'idz2'
  AND table = 'orders_flat'
  AND active
FORMAT TabSeparatedWithNames;

SELECT
    partition,
    count() AS parts_count,
    sum(rows) AS rows,
    formatReadableSize(sum(bytes_on_disk)) AS size_on_disk
FROM system.parts
WHERE database = 'idz2'
  AND table = 'orders_flat'
  AND active
GROUP BY partition
ORDER BY partition
FORMAT TabSeparatedWithNames;