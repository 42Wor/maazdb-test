# benchmarked

1000 operations WRITE/READ
| Language           | Write Time | Write Ops/sec       | Read Time | Read Ops/sec        |
| ----------------   | ---------- | ------------------- | --------- | ------------------- |
| **Python**         | 0.2240s    | 4464 ops/sec        | 0.5265s   | 1899 ops/sec        |
| **Node.js**        | 0.2852s    | 3506 ops/sec        | 0.5456s   | 1833 ops/sec        |
| **Rust (debug)**   | 0.2763s    | 3619 ops/sec        | 0.5897s   | 1696 ops/sec        |
| **Rust (release)** | 0.2257s    | 4429 ops/sec        | 0.5823s   | 1717 ops/sec        |