DROP TABLE IF EXISTS products;

CREATE TABLE products (
    title         text,
    description   text,
    category      string,
    brand         string,
    price         float,
    rating        float,
    reviews_count integer,
    in_stock      bool,
    tags          json,
    created_at    timestamp
) morphology='stem_enru' min_word_len='2' html_strip='1';