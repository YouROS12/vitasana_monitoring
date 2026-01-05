import sqlite3

conn = sqlite3.connect('vitasana.db')
c = conn.cursor()

# Get all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = c.fetchall()

print("=" * 50)
print("DATABASE STRUCTURE")
print("=" * 50)

for (table_name,) in tables:
    print(f"\n[TABLE] {table_name}")
    print("-" * 40)
    c.execute(f"PRAGMA table_info({table_name})")
    columns = c.fetchall()
    for col in columns:
        col_id, name, dtype, notnull, default, pk = col
        pk_marker = " (PRIMARY KEY)" if pk else ""
        print(f"  {name} ({dtype}){pk_marker}")
    
    # Row count
    c.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = c.fetchone()[0]
    print(f"  [Rows: {count:,}]")

conn.close()
