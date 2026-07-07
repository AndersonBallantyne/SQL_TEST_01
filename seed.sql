-- seed.sql — sample data for the customers/orders demo (PostgreSQL)
-- Idempotent: wipes and reloads, so re-running always yields the same rows.

TRUNCATE TABLE orders, customers RESTART IDENTITY;

INSERT INTO customers (name, email) VALUES
    ('Ada Lovelace',      'ada@example.com'),
    ('Alan Turing',       'alan@example.com'),
    ('Grace Hopper',      'grace@example.com'),
    ('Katherine Johnson', 'katherine@example.com');

INSERT INTO orders (customer_id, product, amount) VALUES
    (1, 'Keyboard',     79.99),
    (1, 'Monitor',     249.00),
    (2, 'Mouse',        29.50),
    (3, 'Laptop Stand', 45.00),
    (3, 'USB-C Hub',    34.99);