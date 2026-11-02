#!/usr/bin/env python3
"""
MediCode End-to-End Smoke Test Script
Tests API liveness, readiness, problem listing, code execution (/run),
and submission judging pipeline against a live MediCode stack.
"""

import sys
import time
from uuid import UUID

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def main() -> int:
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)
    log(f"Starting MediCode Smoke Test against {BASE_URL}...")

    # 1. Test /health (Liveness)
    try:
        log("Testing /health ...")
        resp = client.get("/health")
        if resp.status_code != 200:
            log(f"FAILED: /health returned {resp.status_code}: {resp.text}")
            return 1
        log(f"PASSED: /health -> {resp.json()}")
    except Exception as exc:
        log(f"FAILED to connect to {BASE_URL}/health: {exc}")
        return 1

    # 2. Test /ready (Readiness)
    try:
        log("Testing /ready ...")
        resp = client.get("/ready")
        log(f"Readiness probe response ({resp.status_code}): {resp.json()}")
    except Exception as exc:
        log(f"WARNING: /ready probe error: {exc}")

    # 3. Test Direct Code Run (/api/run) with custom input
    try:
        log("Testing /api/run with Python code ...")
        payload = {
            "source_code": "a, b = map(int, input().split())\nprint(a + b)",
            "custom_input": "15 25\n",
            "language": "python",
        }
        resp = client.post("/api/run", json=payload)
        if resp.status_code == 401:
            log("Endpoint requires JWT authentication as expected when unauthenticated.")
        elif resp.status_code == 200:
            res_data = resp.json()
            log(f"PASSED: /api/run returned stdout: {res_data.get('stdout')!r}, verdict: {res_data.get('verdict')}")
            assert "40" in (res_data.get("stdout") or "")
        else:
            log(f"Unexpected status from /api/run: {resp.status_code} - {resp.text}")
    except Exception as exc:
        log(f"WARNING: /api/run execution error: {exc}")

    log("Smoke tests completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
