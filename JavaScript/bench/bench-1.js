const MaazDB = require('maazdb-js');
const { performance } = require('perf_hooks');

// Configuration
const ITERATIONS = 1000;
const DB_HOST = "127.0.0.1";
const DB_PORT = 8888;
const DB_USER = "admin";
const DB_PASS = "admin";

async function main() {
    const db = new MaazDB();

    try {
        // --- 1. Connect ---
        console.log(`Connecting to ${DB_HOST}:${DB_PORT}...`);
        await db.connect(DB_HOST, DB_PORT, DB_USER, DB_PASS);
        console.log("[OK] Connected.");

        // --- 2. Setup ---
        try {
            await db.query("CREATE DATABASE bench_db;");
        } catch (e) {}

        await db.query("USE bench_db;");

        try {
            await db.query("DROP TABLE users_bench_js;");
        } catch (e) {}

        await db.query(
            "CREATE TABLE users_bench_js (id SERIAL PRIMARY KEY, username TEXT);"
        );

        // --- 3. WRITE Benchmark ---
        console.log(`\n--- Starting WRITE Benchmark (${ITERATIONS} operations) ---`);
        const startWrite = performance.now();

        for (let i = 0; i < ITERATIONS; i++) {
            await db.query(
                `INSERT INTO users_bench_js (username) VALUES ('user_${i}');`
            );
        }

        const durationWrite = (performance.now() - startWrite) / 1000;
        const opsWrite = ITERATIONS / durationWrite;

        console.log(`[OK] Inserted ${ITERATIONS} records in ${durationWrite.toFixed(4)} seconds.`);
        console.log(`Write Speed: ${opsWrite.toFixed(2)} ops/sec`);

        // --- 4. READ Benchmark ---
        console.log(`\n--- Starting READ Benchmark (${ITERATIONS} operations) ---`);
        const startRead = performance.now();

        for (let i = 0; i < ITERATIONS; i++) {
            await db.query(
                `SELECT * FROM users_bench_js WHERE username = 'user_${i}';`
            );
        }

        const durationRead = (performance.now() - startRead) / 1000;
        const opsRead = ITERATIONS / durationRead;

        console.log(`[OK] Read ${ITERATIONS} records in ${durationRead.toFixed(4)} seconds.`);
        console.log(`Read Speed: ${opsRead.toFixed(2)} ops/sec`);

    } catch (error) {
        console.error("[ERROR]", error.message);
    } finally {
        db.close();
        console.log("\nConnection closed.");
    }
}

main();