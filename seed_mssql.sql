USE appdb;
GO
DELETE FROM orders;
DELETE FROM customers;
DBCC CHECKIDENT ('customers', RESEED, 0);
DBCC CHECKIDENT ('orders', RESEED, 0);
GO
INSERT INTO customers (name, email) VALUES
    ('Ada Lovelace',      'ada@example.com'),
    ('Alan Turing',       'alan@example.com'),
    ('Grace Hopper',      'grace@example.com'),
    ('Katherine Johnson', 'katherine@example.com');
GO
INSERT INTO orders (customer_id, product, amount)
SELECT c.id, v.product, v.amount
FROM (VALUES
    ('ada@example.com',   'Keyboard',     79.99),
    ('ada@example.com',   'Monitor',     249.00),
    ('alan@example.com',  'Mouse',        29.50),
    ('grace@example.com', 'Laptop Stand', 45.00),
    ('grace@example.com', 'USB-C Hub',    34.99)
) AS v(email, product, amount)
JOIN customers c ON c.email = v.email;
GO