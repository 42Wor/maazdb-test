use maazdb_rs::MaazDB;
use std::error::Error;

fn main() -> Result<(), Box<dyn Error>> {
    // 1. Establish a Secure Connection
    let mut db = MaazDB::connect("127.0.0.1", 8888, "admin", "admin")?;
    println!("✓ Connected to MaazDB via TLS 1.3");

    // 2. Execute SQL Commands
    db.query("CREATE DATABASE store_prod;")?;
    db.query("USE store_prod;")?;
    db.query("CREATE TABLE users (id SERIAL PRIMARY KEY, name TEXT);")?;

    // 3. Insert Data
    db.query("INSERT INTO users (name) VALUES ('Maaz');")?;
    
    // 4. Fetch Results
    let results = db.query("SELECT * FROM users;")?;
    println!("--- Query Results ---\n{}", results);

    Ok(())
}