import sys
import time
import maazdb  # Assuming the python binding is named 'maazdb'

# Force UTF-8 (extra safety)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Configuration
ITERATIONS = 1000
DB_HOST = "127.0.0.1"
DB_PORT = 8888
DB_USER = "admin"
DB_PASS = "admin"


def main():
    db = maazdb.MaazDB()

    try:
        # --- 1. Connect ---
        print(f"Connecting to {DB_HOST}:{DB_PORT}...")
        db.connect(DB_HOST, DB_PORT, DB_USER, DB_PASS)
        print("[OK] Connected.")

        # --- 2. Setup ---
        try:
            db.query("CREATE DATABASE bench_db;")
        except Exception:
            pass

        db.query("USE bench_db;")

        try:
            db.query("DROP TABLE users_bench_py;")
        except Exception:
            pass

        db.query(
            "CREATE TABLE users_bench_py (id SERIAL PRIMARY KEY, username TEXT);"
        )

        # --- 3. WRITE Benchmark ---
        print(f"\n--- Starting WRITE Benchmark ({ITERATIONS} operations) ---")
        start_write = time.perf_counter()

        for i in range(ITERATIONS):
            db.query(
                f"INSERT INTO users_bench_py (username) VALUES ('user_{i}');"
            )

        duration_write = time.perf_counter() - start_write
        ops_write = ITERATIONS / duration_write

        print(f"[OK] Inserted {ITERATIONS} records in {duration_write:.4f} seconds.")
        print(f"Write Speed: {ops_write:.2f} ops/sec")

        # --- 4. READ Benchmark ---
        print(f"\n--- Starting READ Benchmark ({ITERATIONS} operations) ---")
        start_read = time.perf_counter()

        for i in range(ITERATIONS):
            db.query(
                f"SELECT * FROM users_bench_py WHERE username = 'user_{i}';"
            )

        duration_read = time.perf_counter() - start_read
        ops_read = ITERATIONS / duration_read

        print(f"[OK] Read {ITERATIONS} records in {duration_read:.4f} seconds.")
        print(f"Read Speed: {ops_read:.2f} ops/sec")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        try:
            db.close()
        except Exception:
            pass
        print("\nConnection closed.")


if __name__ == "__main__":
    main()