from database import engine

try:
    conn = engine.connect()
    print("✅ Connected to Neon PostgreSQL!")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")