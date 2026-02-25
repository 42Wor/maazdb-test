use std::time::Instant;
use maazdb_rs::MaazDB; 

const ITERATIONS: usize = 1000;
const DB_HOST: &str = "127.0.0.1";
const DB_PORT: u16 = 8888;
const DB_USER: &str = "admin";
const DB_PASS: &str = "admin";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 1. Connect (The driver returns the instance directly via connect)
    println!("Connecting to {}:{}...", DB_HOST, DB_PORT);
    let mut db = MaazDB::connect(DB_HOST, DB_PORT, DB_USER, DB_PASS)?;
    println!("✓ Connected.");

    // 2. Setup
    // Ignore errors on setup queries if DB/Table already exists
    let _ = db.query("CREATE DATABASE bench_db;");
    db.query("USE bench_db;")?;
    let _ = db.query("DROP TABLE users_bench_rs;");
    
    db.query("CREATE TABLE users_bench_rs (id SERIAL PRIMARY KEY, username TEXT);")?;

    // 3. Benchmark: WRITES
    println!("\n--- Starting WRITE Benchmark ({} operations) ---", ITERATIONS);
    let start_write = Instant::now();

    for i in 0..ITERATIONS {
        let sql = format!("INSERT INTO users_bench_rs (username) VALUES ('user_{}');", i);
        db.query(&sql)?;
    }

    let duration_write = start_write.elapsed();
    let ops_write = ITERATIONS as f64 / duration_write.as_secs_f64();

    println!("✓ Inserted {} records in {:.4} seconds.", ITERATIONS, duration_write.as_secs_f64());
    println!("🚀 Write Speed: {:.2} ops/sec", ops_write);

    // 4. Benchmark: READS
    println!("\n--- Starting READ Benchmark ({} operations) ---", ITERATIONS);
    let start_read = Instant::now();

    for i in 0..ITERATIONS {
        let sql = format!("SELECT * FROM users_bench_rs WHERE username = 'user_{}';", i);
        db.query(&sql)?;
    }

    let duration_read = start_read.elapsed();
    let ops_read = ITERATIONS as f64 / duration_read.as_secs_f64();

    println!("✓ Read {} records in {:.4} seconds.", ITERATIONS, duration_read.as_secs_f64());
    println!("🚀 Read Speed: {:.2} ops/sec", ops_read);

    // 5. Cleanup
    db.close();
    println!("\nConnection closed.");

    Ok(())
}