
import sqlite3

conn = sqlite3.connect("lotia.db")

conn.execute("""
CREATE TABLE IF NOT EXISTS historical_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT
)
""")

conn.commit()
conn.close()

print("HistoricalPeriods 表创建成功！")
