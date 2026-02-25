import sys
sys.stdout.reconfigure(encoding='utf-8')

import subprocess
import re
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent

RESULTS = []

def run_command(label, command, cwd):
    print(f"\n=== Running {label} ===")
    start = time.time()

    process = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        shell=True,
        encoding="utf-8",    
        errors="replace"      
    )

    duration = time.time() - start
    output = process.stdout + process.stderr

    write_speed = extract_speed(output, "Write Speed")
    read_speed = extract_speed(output, "Read Speed")

    RESULTS.append({
        "name": label,
        "write": write_speed,
        "read": read_speed,
        "time": round(duration, 2)
    })

    print(output)


def extract_speed(text, label):
    match = re.search(rf"{label}:\s+([\d.]+)", text)
    return float(match.group(1)) if match else 0.0


def print_summary():
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)

    print(f"{'Runtime':<20} {'Write ops/sec':<15} {'Read ops/sec':<15} {'Total Time'}")
    print("-" * 60)

    for r in RESULTS:
        print(f"{r['name']:<20} {r['write']:<15.2f} {r['read']:<15.2f} {r['time']}s")

    print("=" * 60)


if __name__ == "__main__":

    # Node.js
    run_command(
        "Node.js",
        "node bench/bench-1.js",
        BASE_DIR / "JavaScript"
    )

    # Python
    run_command(
        "Python",
        "py bench/bench-1.py",
        BASE_DIR / "python"
    )

    # Rust Debug
    run_command(
        "Rust (debug)",
        "cargo run --bin bench-1",
        BASE_DIR / "rust"
    )

    # Rust Release
    run_command(
        "Rust (release)",
        "cargo run --release --bin bench-1",
        BASE_DIR / "rust"
    )

    print_summary()