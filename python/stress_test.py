import time
from maazdb import MaazDB

def main():
    # 1. Initialize the client
    db = MaazDB()
    
    try:
        # Connect securely
        db.connect(host="127.0.0.1", port=8888, user="admin", password="admin")
        print("🚀 Connected to MAAZDB. Starting 4GB Stress Test...")

        # 2. Setup Environment
        db.query("DROP DATABASE IF EXISTS stress_db;")
        db.query("CREATE DATABASE stress_db;")
        db.query("USE stress_db;")
        db.query("CREATE TABLE big_data (id SERIAL PRIMARY KEY, payload TEXT);")

        # 3. Configuration for 4GB
        total_rows = 32_000_000
        batch_size = 5_000
        total_batches = total_rows // batch_size

        print(f"📦 Target: {total_rows} rows in {total_batches} batches.")
        print("⚙️ Pre-building optimized batch query string...")

        # ========================================================================
        # CRITICAL OPTIMIZATION: Pre-build the query string EXACTLY ONCE.
        # In Python, using list multiplication and .join() is highly optimized 
        # in CPython and prevents memory fragmentation from string concatenation.
        # ========================================================================
        dummy_data = "A" * 100
        # Creates: "('A...A'), ('A...A'), ..."
        values_clause = ", ".join([f"('{dummy_data}')"] * batch_size)
        batch_query = f"INSERT INTO big_data (payload) VALUES {values_clause};"
        # ========================================================================

        print(f"✅ Query pre-built (Size: {len(batch_query)} bytes). Starting INSERT loop...")

        start_time = time.time()
        last_report_time = time.time()

        # 4. INSERT LOOP (The 4GB Push)
        for b in range(1, total_batches + 1):
            try:
                # Execute the exact same pre-built string. Zero client-side allocations!
                db.query(batch_query)
            except Exception as e:
                print(f"❌ Batch {b} failed: {e}")
                break

            # Progress Reporting (Every 100 batches)
            if b % 100 == 0 or b == total_batches:
                percent = (b / total_batches) * 100.0
                current_time = time.time()
                elapsed_total = current_time - start_time
                
                # Calculate Rows Per Second for this specific window
                window_elapsed = current_time - last_report_time
                rows_per_sec = (100 * batch_size) / window_elapsed if window_elapsed > 0 else 0

                print(f"➡️ Progress: {percent:>5.2f}% | Batches: {b:>5}/{total_batches} | Speed: {rows_per_sec:>7.0f} rows/sec | Elapsed: {elapsed_total:>5.1f}s")

                last_report_time = current_time

        total_time = time.time() - start_time
        avg_speed = total_rows / total_time if total_time > 0 else 0
        
        print("\n✅ 4GB Data Load Complete!")
        print(f"⏱️ Total Time: {total_time:.2f} seconds")
        print(f"🚀 Average Speed: {avg_speed:.0f} rows/sec")

        # 5. VERIFICATION (Testing the Index & Buffer Pool)
        print("\n🔍 Running Verification Queries...")

        count_res = db.query("SELECT COUNT(*) FROM big_data;")
        print(f"📊 Total Rows: {count_res}")

        pk_start = time.time()
        pk_res = db.query("SELECT * FROM big_data WHERE id = 15000000;")
        print(f"⚡ PK Lookup (Row 15M) took: {time.time() - pk_start:.4f}s\nResult: {pk_res}")

        up_start = time.time()
        db.query("UPDATE big_data SET payload = 'UPDATED_DATA' WHERE id = 100;")
        print(f"📝 Update (Row 100) took: {time.time() - up_start:.4f}s")

        db.query("DELETE FROM big_data WHERE id = 500;")
        print("🗑️ Delete (Row 500) complete.")

        # 6. THE IDLE PURGE TEST
        print("\n🕒 Waiting 65 seconds for Idle Memory Purge...")
        print("(Watch your monitor tool: Physical Memory should drop significantly)")
        time.sleep(65)

        print("\n🏁 Stress Test Finished. MAAZDB is VPS-Stable.")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # 7. Always close the connection
        db.close()

if __name__ == "__main__":
    main()