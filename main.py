# main.py
import os
from datetime import datetime
from math import ceil
from typing import List, Dict, Union, Any

from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

# 從 .env 檔案載入環境變數
load_dotenv()

app = FastAPI(
    title="電子商務訂單管理 API",
    description="用於管理訂單、產品和訂單統計的 API。",
    version="1.0.0"
)

# 資料庫連線設定
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "ecommerce_test")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "") # 在實際生產環境中，請使用環境變數

def get_db_connection():
    """建立並回傳資料庫連線。"""
    conn = None
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        if conn.is_connected():
            print("成功連接到資料庫")
        return conn
    except Error as e:
        print(f"連接 MySQL 資料庫時發生錯誤: {e}")
        # 在生產環境中，更穩健地記錄此錯誤
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="伺服器錯誤: 無法連接資料庫"
        )

# Pydantic 模型用於請求和回應驗證/序列化
class OrderItemRequest(BaseModel):
    product_id: int = Field(..., gt=0, description="產品 ID")
    quantity: int = Field(..., gt=0, description="產品數量")

class CreateOrderRequest(BaseModel):
    user_id: int = Field(..., gt=0, description="下訂單的使用者 ID")
    items: List[OrderItemRequest] = Field(..., min_items=1, description="訂單中的商品清單")

class OrderResponse(BaseModel):
    id: int
    user_id: int
    number: str
    status: str
    total_amount: float
    created_at: datetime

class OrderListResponse(BaseModel):
    data: List[OrderResponse]
    page: int
    total_pages: int
    total_items: int

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    stock: int

class ProductListResponse(BaseModel):
    data: List[ProductResponse]
    page: int
    total_pages: int
    total_items: int

class OrderStatsResponse(BaseModel):
    total_orders: int
    total_amount: float
    today_orders: int
    today_amount: float

class UpdateOrderStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(pending|processing|shipped|delivered|cancelled)$", description="訂單的新狀態")

# 依賴項，用於獲取資料庫連線並確保其關閉
def get_db():
    db = get_db_connection()
    try:
        yield db
    finally:
        if db:
            db.close()

# API 路由

@app.get("/api/orders", response_model=OrderListResponse, summary="獲取分頁的訂單列表")
async def get_orders(page: int = 1, limit: int = 20, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    擷取分頁的訂單列表。
    """
    if limit <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="限制必須是正整數。")
    if page <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="頁碼必須是正整數。")

    offset = (page - 1) * limit
    cursor = db.cursor(dictionary=True)

    try:
        # 獲取總數
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_items = cursor.fetchone()['COUNT(*)']
        total_pages = ceil(total_items / limit) if total_items > 0 else 0

        # 獲取分頁訂單
        cursor.execute(
            "SELECT id, user_id, number, status, total_amount, created_at FROM orders LIMIT %s OFFSET %s",
            (limit, offset)
        )
        orders = cursor.fetchall()

        return {
            "data": orders,
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items
        }
    except Error as e:
        print(f"資料庫錯誤: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="伺服器錯誤: 無法獲取訂單列表")
    finally:
        cursor.close()


@app.get("/api/orders/{order_id}", response_model=OrderResponse, summary="獲取單一訂單的詳細資訊")
async def get_order_details(order_id: int, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    根據訂單 ID 擷取特定訂單的詳細資訊。
    """
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, user_id, number, status, total_amount, created_at FROM orders WHERE id = %s", (order_id,))
        order = cursor.fetchone()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="訂單不存在")
        return order
    except Error as e:
        print(f"資料庫錯誤: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="伺服器錯誤: 無法獲取訂單詳情")
    finally:
        cursor.close()


@app.post("/api/orders", status_code=status.HTTP_201_CREATED, summary="建立新訂單")
async def create_order(order_data: CreateOrderRequest, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    建立新訂單，扣除產品庫存並管理交易。
    """
    cursor = db.cursor()
    try:
        db.start_transaction()

        user_id = order_data.user_id
        # 生成唯一的訂單號 (類似 PHP 的邏輯)
        order_number = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{os.urandom(2).hex()}" # 比 mt_rand 更健壯
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 插入 orders 表
        cursor.execute(
            "INSERT INTO orders (user_id, number, status, created_at, updated_at) VALUES (%s, %s, 'pending', %s, %s)",
            (user_id, order_number, current_time, current_time)
        )
        order_id = cursor.lastrowid
        if not order_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="無法創建訂單")

        total_amount = 0.0

        for item in order_data.items:
            product_id = item.product_id
            quantity = item.quantity

            # 鎖定產品行以進行更新，防止競爭條件 (FOR UPDATE 等效)
            # 在 mysql.connector 中，通常透過確保事務隱式持有鎖定來處理此問題，透過 UPDATE/SELECT FOR UPDATE。
            # 這裡我們將先進行 SELECT，然後進行 UPDATE，依賴於事務。
            cursor.execute("SELECT stock, price, is_deleted FROM products WHERE id = %s FOR UPDATE", (product_id,))
            product = cursor.fetchone()

            if not product:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"產品 ID {product_id} 不存在")
            
            product_stock, product_price, is_deleted = product[0], product[1], product[2] # 透過索引存取非字典游標

            if is_deleted:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"產品 ID {product_id} 已停用或刪除")

            if product_stock < quantity:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"產品 ID {product_id} 庫存不足。可用: {product_stock}, 需求: {quantity}")

            unit_price = float(product_price)
            subtotal = unit_price * quantity
            total_amount += subtotal

            # 更新產品庫存
            cursor.execute(
                "UPDATE products SET stock = stock - %s, updated_at = %s WHERE id = %s AND stock >= %s",
                (quantity, current_time, product_id, quantity)
            )
            if cursor.rowcount == 0:
                 # 如果初始檢查後庫存不足，則可能會發生這種情況，因為存在競爭條件
                db.rollback() # 在拋出異常前明確回滾
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"產品 ID {product_id} 庫存更新失敗，可能庫存不足或並發問題")

            # 插入 order_items
            cursor.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (order_id, product_id, quantity, unit_price, subtotal, current_time, current_time)
            )

        # 更新 orders 表中的總金額
        cursor.execute("UPDATE orders SET total_amount = %s WHERE id = %s", (total_amount, order_id))

        db.commit()
        return {"order_id": order_id, "order_number": order_number}

    except HTTPException as e:
        db.rollback()
        raise e # 重新拋出 FastAPI HTTPException
    except Error as e:
        db.rollback()
        print(f"訂單創建期間的資料庫錯誤: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"伺服器錯誤: 無法創建訂單。詳細錯誤: {e}" # 開發環境中更詳細，生產環境中更通用
        )
    except Exception as e:
        db.rollback()
        print(f"訂單創建期間發生意外錯誤: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"伺服器錯誤: {e}")
    finally:
        cursor.close()


@app.put("/api/orders/{order_id}/status", summary="更新訂單狀態")
async def update_order_status(order_id: int, status_data: UpdateOrderStatusRequest, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    更新特定訂單的狀態。
    允許的狀態: 'pending'、'processing'、'shipped'、'delivered'、'cancelled'。
    """
    cursor = db.cursor()
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "UPDATE orders SET status = %s, updated_at = %s WHERE id = %s",
            (status_data.status, current_time, order_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="訂單不存在或狀態已是目標狀態")
        db.commit()
        return {"success": True, "message": "訂單狀態更新成功"}
    except Error as e:
        db.rollback()
        print(f"資料庫錯誤: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="伺服器錯誤: 無法更新訂單狀態")
    finally:
        cursor.close()


@app.get("/api/orders/stats", response_model=OrderStatsResponse, summary="獲取訂單統計")
async def get_order_stats(db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    擷取訂單的聚合統計資訊，包括總訂單數、總金額、今日訂單數和今日金額。
    """
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM orders) as total_orders,
                (SELECT COALESCE(SUM(total_amount), 0) FROM orders) as total_amount,
                (SELECT COUNT(*) FROM orders WHERE DATE(created_at) = CURDATE()) as today_orders,
                (SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE DATE(created_at) = CURDATE()) as today_amount
        """)
        stats = cursor.fetchone()

        # 確保正確的類型並處理如果沒有訂單時總和可能為 None 的情況
        return OrderStatsResponse(
            total_orders=int(stats['total_orders']),
            total_amount=float(stats['total_amount']),
            today_orders=int(stats['today_orders']),
            today_amount=float(stats['today_amount'])
        )
    except Error as e:
        print(f"資料庫錯誤: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="伺服器錯誤: 無法獲取訂單統計")
    finally:
        cursor.close()


@app.get("/api/products", response_model=ProductListResponse, summary="獲取分頁的產品列表")
async def get_products(page: int = 1, limit: int = 50, db: mysql.connector.connection.MySQLConnection = Depends(get_db)):
    """
    擷取活躍產品 (is_deleted = FALSE) 的分頁列表。
    """
    if limit <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="限制必須是正整數。")
    if page <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="頁碼必須是正整數。")

    offset = (page - 1) * limit
    cursor = db.cursor(dictionary=True)

    try:
        # 獲取活躍產品的總數
        cursor.execute("SELECT COUNT(*) FROM products WHERE is_deleted = FALSE")
        total_items = cursor.fetchone()['COUNT(*)']
        total_pages = ceil(total_items / limit) if total_items > 0 else 0

        # 獲取分頁產品
        cursor.execute(
            "SELECT id, name, price, stock FROM products WHERE is_deleted = FALSE LIMIT %s OFFSET %s",
            (limit, offset)
        )
        products = cursor.fetchall()

        return {
            "data": products,
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items
        }
    except Error as e:
        print(f"資料庫錯誤: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="伺服器錯誤: 無法獲取產品列表")
    finally:
        cursor.close()
