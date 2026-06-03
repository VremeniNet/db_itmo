
SELECT
    product_id,
    product_name,
    category,
    sum(quantity) AS total_qty,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
GROUP BY
    product_id,
    product_name,
    category
ORDER BY total_revenue DESC
LIMIT 10
FORMAT PrettyCompact;



SELECT
    toStartOfMonth(order_date) AS month,
    category,
    sum(quantity) AS total_qty,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
GROUP BY
    month,
    category
ORDER BY
    month,
    category
FORMAT PrettyCompact;



WITH order_totals AS (
    SELECT
        order_id,
        sum(toFloat64(line_total)) AS order_total
    FROM idz2.orders_flat
    GROUP BY order_id
)
SELECT
    quantileExact(0.95)(order_total) AS p95_order_value,
    quantileExact(0.99)(order_total) AS p99_order_value,
    avg(order_total) AS avg_order_value,
    count() AS orders_count
FROM order_totals
FORMAT PrettyCompact;



SELECT
    customer_id,
    customer_name,
    customer_email,
    count() AS rows_count,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
WHERE positionCaseInsensitive(customer_email, 'ivanov') > 0
GROUP BY
    customer_id,
    customer_name,
    customer_email
ORDER BY rows_count DESC
FORMAT PrettyCompact;



SELECT
    toStartOfMonth(order_date) AS month,
    category,
    region,
    sum(toUInt64(quantity)) AS total_qty,
    sum(line_total) AS total_revenue
FROM idz2.orders_flat
GROUP BY
    month,
    category,
    region
ORDER BY
    month,
    category,
    region
LIMIT 20
FORMAT PrettyCompact;



SELECT
    month,
    category,
    region,
    sum(total_qty) AS total_qty,
    sum(total_revenue) AS total_revenue
FROM idz2.monthly_sales
GROUP BY
    month,
    category,
    region
ORDER BY
    month,
    category,
    region
LIMIT 20
FORMAT PrettyCompact;