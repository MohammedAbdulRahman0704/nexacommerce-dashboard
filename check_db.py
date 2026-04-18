import sqlite3

conn = sqlite3.connect(r"D:\Python Projects\Project - 1\data\nexacommerce.db")

tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()

for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
    print(f"{t[0]:15} → {count:,} rows")

conn.close()