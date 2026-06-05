CREATE TABLE idz4.events_distributed ON CLUSTER cluster_2x2
AS idz4.events_local
ENGINE = Distributed(
    'cluster_2x2',
    'idz4',
    'events_local',
    xxHash64(user_id)
);