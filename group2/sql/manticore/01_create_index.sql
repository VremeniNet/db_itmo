DROP TABLE IF EXISTS reviews;

CREATE TABLE reviews (
    title       text,
    body        text,
    product_id  integer,
    customer_id integer,
    rating      integer,
    created_at  timestamp
)
morphology='stem_enru'
min_word_len='2';