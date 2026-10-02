import sqlite3
import os

db_path = 'yomi.db'
if not os.path.exists(db_path):
    print(f"Database file not found at {os.path.abspath(db_path)}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables in database:")
    for table in tables:
        print(table[0])
    conn.close()
