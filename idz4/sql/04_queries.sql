SELECT
    count() AS distributed_count
FROM idz4.events_distributed;


SELECT
    user_id,
    count() AS events_count,
    sum(duration_ms) AS total_duration_ms
FROM idz4.events_distributed
GROUP BY user_id
ORDER BY
    events_count DESC,
    user_id
LIMIT 10;


SELECT
    page_url,
    count() AS visits,
    uniqExact(user_id) AS users_count,
    round(avg(duration_ms), 2) AS avg_duration_ms
FROM idz4.events_distributed
GROUP BY page_url
ORDER BY
    visits DESC,
    page_url
LIMIT 10;



SELECT
    u.segment,
    count() AS events_count,
    uniqExact(e.user_id) AS users_count,
    round(avg(e.duration_ms), 2) AS avg_duration_ms
FROM idz4.events_distributed AS e
INNER JOIN idz4.user_dict AS u
    ON e.user_id = u.user_id
GROUP BY u.segment
ORDER BY events_count DESC;



SELECT
    count() AS vip_events
FROM idz4.events_distributed
WHERE user_id GLOBAL IN (
    SELECT user_id
    FROM idz4.user_dict_distributed
    WHERE segment = 'vip'
);