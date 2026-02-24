from maazdb import MaazDB

# 1. Initialize the client
db = MaazDB()

try:
    # 2. Connect securely
    db.connect(host="127.0.0.1", port=8888, user="admin", password="admin")
    print("✓ Connected to MaazDB")

    # 3. Execute SQL
    db.query("CREATE DATABASE analytics;")
    db.query("USE analytics;")
    db.query("CREATE TABLE logs (id SERIAL PRIMARY KEY, message TEXT);")
    
    # 4. Insert and Fetch
    db.query("INSERT INTO logs (message) VALUES ('System started');")
    results = db.query("SELECT * FROM logs;")
    print(f"Results:\n{results}")

except Exception as e:
    print(f"An error occurred: {e}")

finally:
    # 5. Always close the connection
    db.close()