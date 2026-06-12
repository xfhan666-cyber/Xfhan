"""
SQLite本地缓存层 - 存储历史K线和财务数据，减少重复API调用
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from config import CACHE_DB


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(CACHE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS daily_kline (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL,
            PRIMARY KEY (code, date)
        );

        CREATE TABLE IF NOT EXISTS stock_basic (
            code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            market_cap REAL,
            pe_ratio REAL,
            pb_ratio REAL,
            update_time TEXT
        );

        CREATE TABLE IF NOT EXISTS financial_data (
            code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            roe REAL, roa REAL,
            revenue_growth REAL, profit_growth REAL,
            gross_margin REAL, net_margin REAL,
            debt_ratio REAL,
            dividend_yield REAL,
            PRIMARY KEY (code, report_date)
        );

        CREATE TABLE IF NOT EXISTS cache_meta (
            cache_key TEXT PRIMARY KEY,
            cache_value TEXT,
            expire_time TEXT
        );
    ''')

    conn.commit()
    conn.close()


def save_daily_kline(code, df):
    """保存日K线到缓存"""
    if df is None or df.empty:
        return
    conn = get_connection()
    df.to_sql('daily_kline', conn, if_exists='append', index=False)
    conn.close()


def load_daily_kline(code, start_date=None, end_date=None):
    """从缓存加载日K线"""
    conn = get_connection()
    query = "SELECT * FROM daily_kline WHERE code = ?"
    params = [code]
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def save_stock_basic(df):
    """保存股票基本信息"""
    if df is None or df.empty:
        return
    conn = get_connection()
    df.to_sql('stock_basic', conn, if_exists='replace', index=False)
    conn.close()


def load_stock_basic():
    """加载股票基本信息"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM stock_basic", conn)
    conn.close()
    return df


def save_financial_data(code, df):
    """保存财务数据"""
    if df is None or df.empty:
        return
    conn = get_connection()
    df['code'] = code
    df.to_sql('financial_data', conn, if_exists='append', index=False)
    conn.close()


def load_financial_data(code=None):
    """加载财务数据"""
    conn = get_connection()
    if code:
        df = pd.read_sql_query("SELECT * FROM financial_data WHERE code = ? ORDER BY report_date DESC", conn, params=[code])
    else:
        df = pd.read_sql_query("SELECT * FROM financial_data ORDER BY report_date DESC", conn)
    conn.close()
    return df


def set_cache(key, value, expire_minutes=60):
    """设置通用缓存"""
    conn = get_connection()
    expire_time = datetime.now() + timedelta(minutes=expire_minutes)
    conn.execute('''INSERT OR REPLACE INTO cache_meta (cache_key, cache_value, expire_time)
                    VALUES (?, ?, ?)''', (key, str(value), expire_time.isoformat()))
    conn.commit()
    conn.close()


def get_cache(key):
    """获取通用缓存"""
    conn = get_connection()
    row = conn.execute("SELECT cache_value, expire_time FROM cache_meta WHERE cache_key = ?", [key]).fetchone()
    conn.close()
    if row and datetime.fromisoformat(row['expire_time']) > datetime.now():
        return row['cache_value']
    return None


# 初始化数据库
init_db()
