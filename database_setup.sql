-- E-commerce Order Management System - Database Setup
-- 電子商務訂單管理系統 - 資料庫設定
-- This file creates the database and table structure
-- 此檔案用於建立資料庫及資料表結構

-- Create database
-- 建立資料庫
CREATE DATABASE IF NOT EXISTS ecommerce_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Use database
-- 使用資料庫
USE ecommerce_test;

-- Create users table
-- 建立使用者資料表
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT, -- 使用者ID，主鍵，自動遞增
    name VARCHAR(100) NOT NULL, -- 使用者名稱，不可為空
    email VARCHAR(100) NOT NULL UNIQUE, -- 電子郵件，不可為空，唯一
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- 建立時間，預設為當前時間
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 更新時間，預設為當前時間並在更新時自動更新
    INDEX idx_email (email) -- 為電子郵件欄位建立索引
);

-- Create products table
-- 建立產品資料表
CREATE TABLE products (
    id INT PRIMARY KEY AUTO_INCREMENT, -- 產品ID，主鍵，自動遞增
    name VARCHAR(100) NOT NULL, -- 產品名稱，不可為空
    price DECIMAL(10, 2) NOT NULL, -- 產品價格，不可為空，小數點前後共10位，小數點後2位
    stock INT NOT NULL DEFAULT 0, -- 庫存數量，不可為空，預設為0
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- 建立時間，預設為當前時間
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 更新時間，預設為當前時間並在更新時自動更新
    is_deleted BOOLEAN DEFAULT FALSE, -- 產品是否已刪除，預設為否
    INDEX idx_name (name), -- 為產品名稱欄位建立索引
    INDEX idx_price (price), -- 為產品價格欄位建立索引
    CONSTRAINT chk_stock CHECK (stock >= 0) -- 檢查庫存數量必須大於或等於0
);

-- Create orders table
-- 建立訂單資料表
CREATE TABLE orders (
    id INT PRIMARY KEY AUTO_INCREMENT, -- 訂單ID，主鍵，自動遞增
    user_id INT NOT NULL, -- 使用者ID，不可為空
    number VARCHAR(50) NOT NULL UNIQUE, -- 訂單編號，不可為空，唯一
    status ENUM('pending', 'processing', 'shipped', 'delivered', 'cancelled') NOT NULL DEFAULT 'pending', -- 訂單狀態，不可為空，預設為'pending' (待處理)
    total_amount DECIMAL(10, 2) NOT NULL DEFAULT 0.00, -- 訂單總金額，不可為空，預設為0.00
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- 建立時間，預設為當前時間
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 更新時間，預設為當前時間並在更新時自動更新
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, -- 外來鍵關聯至users表的id，當users刪除時，相關訂單也刪除
    INDEX idx_user_id (user_id), -- 為使用者ID欄位建立索引
    INDEX idx_status (status), -- 為訂單狀態欄位建立索引
    INDEX idx_created_at (created_at), -- 為建立時間欄位建立索引
    INDEX idx_total_amount (total_amount) -- 為訂單總金額欄位建立索引
);

-- Create order_items table
-- 建立訂單項目資料表
CREATE TABLE order_items (
    id INT PRIMARY KEY AUTO_INCREMENT, -- 訂單項目ID，主鍵，自動遞增
    order_id INT NOT NULL, -- 訂單ID，不可為空
    product_id INT NOT NULL, -- 產品ID，不可為空
    quantity INT NOT NULL DEFAULT 1, -- 購買數量，不可為空，預設為1
    unit_price DECIMAL(10, 2) NOT NULL, -- 商品單價，不可為空
    subtotal DECIMAL(10, 2) NOT NULL, -- 小計金額，不可為空
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- 建立時間，預設為當前時間
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, -- 更新時間，預設為當前時間並在更新時自動更新
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE, -- 外來鍵關聯至orders表的id，當orders刪除時，相關訂單項目也刪除
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL, -- 外來鍵關聯至products表的id，當products刪除時，相關訂單項目的product_id設為NULL
    INDEX idx_order_id (order_id), -- 為訂單ID欄位建立索引
    INDEX idx_product_id (product_id), -- 為產品ID欄位建立索引
    CONSTRAINT chk_quantity CHECK (quantity > 0) -- 檢查購買數量必須大於0
);