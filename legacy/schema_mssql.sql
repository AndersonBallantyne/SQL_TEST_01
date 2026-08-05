IF DB_ID('appdb') IS NULL CREATE DATABASE appdb;
GO
USE appdb;
GO
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
GO
CREATE TABLE customers (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    name        NVARCHAR(200) NOT NULL,
    email       NVARCHAR(200) UNIQUE,
    created_at  DATETIME2 DEFAULT SYSDATETIME()
);
GO
CREATE TABLE orders (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id),
    product     NVARCHAR(200) NOT NULL,
    amount      DECIMAL(10,2) NOT NULL,
    ordered_at  DATETIME2 DEFAULT SYSDATETIME()
);
GO
