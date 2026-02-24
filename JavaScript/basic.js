const MaazDB = require('maazdb-js');

async function main() {
    // 1. Initialize the client
    const db = new MaazDB();

    try {
        // 2. Connect securely (TLS is handled automatically)
        await db.connect("127.0.0.1", 8888, "admin", "admin");
        console.log("✓ Connected to MaazDB");

        // 3. Run SQL commands
        await db.query("CREATE DATABASE web_app;");
        await db.query("USE web_app;");
        
        // 4. Insert Data
        await db.query("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT);");
        await db.query("INSERT INTO users (username) VALUES ('maaz_dev');");

        // 5. Fetch Results
        const results = await db.query("SELECT * FROM users;");
        console.log("Results:", results);

    } catch (error) {
        console.error("Database Error:", error.message);
    } finally {
        // 6. Close connection
        db.close();
    }
}

main();