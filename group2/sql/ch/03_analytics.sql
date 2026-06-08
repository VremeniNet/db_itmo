SELECT 'TOTAL ANALYTICS ROWS' AS section
FORMAT PrettyCompact;

SELECT
    count() AS analytics_rows,
    uniqExact(order_id) AS unique_orders,
    round(sum(toFloat64(line_total)), 2) AS total_revenue
FROM ecommerce.orders_analytics_distributed
FORMAT PrettyCompact;


SELECT 'TOP 5 CATEGORIES BY REVENUE IN LATEST MONTH' AS section
FORMAT PrettyCompact;

WITH
    (
        SELECT max(order_date)
        FROM ecommerce.orders_analytics_distributed
    ) AS max_order_date
SELECT
    category,
    round(sumMerge(revenue), 2) AS total_revenue,
    sumMerge(quantity) AS items_sold
FROM ecommerce.category_revenue_distributed
WHERE order_date >= toStartOfMonth(max_order_date)
  AND order_date <= max_order_date
GROUP BY category
ORDER BY total_revenue DESC
LIMIT 5
FORMAT PrettyCompact;


SELECT 'DAILY ORDER DYNAMICS, LAST 14 DAYS' AS section
FORMAT PrettyCompact;

WITH
    (
        SELECT max(order_date)
        FROM ecommerce.orders_analytics_distributed
    ) AS max_order_date
SELECT
    order_date,
    uniqExactMerge(orders_count) AS orders_count,
    round(sumMerge(revenue), 2) AS revenue
FROM ecommerce.daily_orders_distributed
WHERE order_date >= max_order_date - 13
GROUP BY order_date
ORDER BY order_date
FORMAT PrettyCompact;


SELECT 'REVENUE BY REGION' AS section
FORMAT PrettyCompact;

SELECT
    region,
    uniqExact(order_id) AS orders_count,
    round(sum(toFloat64(line_total)), 2) AS revenue
FROM ecommerce.orders_analytics_distributed
GROUP BY region
ORDER BY revenue DESC
FORMAT PrettyCompact;