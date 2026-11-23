"""
scripts/migrate_user_tables.py — Run migrations and ensure all tables exist in MySQL.
"""

import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("MYSQL_HOST", "localhost")
user = os.getenv("MYSQL_USER", "root")
password = os.getenv("MYSQL_PASSWORD", os.getenv("DB_PASSWORD", "password"))
database = os.getenv("MYSQL_DATABASE", "ai_sdr_db")

conn = pymysql.connect(
    host=host,
    user=user,
    password=password,
    database=database,
    client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS
)

cur = conn.cursor()

# 1. Check existing columns in users table
cur.execute("DESCRIBE users;")
existing_cols = [r[0] for r in cur.fetchall()]

columns_to_add = [
    ("role", "VARCHAR(50) DEFAULT 'admin'"),
    ("is_active", "BOOLEAN DEFAULT TRUE"),
    ("avatar_url", "VARCHAR(500) NULL"),
    ("last_login_at", "TIMESTAMP NULL"),
    ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
]

for col_name, col_def in columns_to_add:
    if col_name not in existing_cols:
        cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};")
        print(f"Added column {col_name} to users table.")

# 2. Execute schema.sql to create user_sessions, password_resets, user_settings, activity_logs
with open("schema.sql", "r", encoding="utf-8") as f:
    sql = f.read()

cur.execute(sql)
conn.commit()

# 3. Check all tables
cur.execute("SHOW TABLES FROM ai_sdr_db;")
tables = [r[0] for r in cur.fetchall()]
print(f"Current tables in ai_sdr_db ({len(tables)} tables):", tables)

cur.execute("DESCRIBE users;")
print("Users table schema:", [(r[0], r[1]) for r in cur.fetchall()])

conn.close()
