TRUNCATE TABLE idz3.events SYNC;

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

SELECT
    hostName() AS node,
    count() AS rows_count,
    min(event_time) AS min_event_time,
    max(event_time) AS max_event_time
FROM idz3.events
FORMAT TabSeparatedWithNames;