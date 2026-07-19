-- 001_schema.sql — PostgreSQL schema for the customers/orders demo (renamed from schema.sql)
-- Running this REBUILDS the tables from scratch. It drops existing data first,
-- which is what you want for a clean, reproducible setup.

-- Drop in child-before-parent order (orders references customers)
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

-- Create parent first, then the table that references it
CREATE TABLE customers (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT UNIQUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE orders (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    product      TEXT NOT NULL,
    amount       NUMERIC(10,2) NOT NULL,
    ordered_at   TIMESTAMPTZ DEFAULT now()
);