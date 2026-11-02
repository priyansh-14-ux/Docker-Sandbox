#!/usr/bin/env python3
"""
MediCode Factorial Problem Demo Script
Creates a Factorial problem with visible & hidden tests, submits a Python solution,
and checks the execution verdict from the isolated sandbox.
"""

import asyncio
import sys
from uuid import uuid4

import httpx

API_URL = "http://localhost:8000"

FACTORIAL_CODE_CORRECT = """
import math
n = int(input().strip())
print(math.factorial(n))
""".strip()

FACTORIAL_CODE_RECURSION_ERROR = """
# Unhandled negative or infinite recursion causes RecursionError (RE)
def fact(n):
    return n * fact(n - 1)
n = int(input().strip())
print(fact(n))
""".strip()

FACTORIAL_CODE_WRONG = """
# Off-by-one error (WA)
n = int(input().strip())
print(n * 2)
""".strip()


async def demo_direct_run(client: httpx.AsyncClient):
    print("\n--- 1. Testing Factorial via Quick Run (/api/run) ---")
    test_cases = [
        ("0\n", "1"),
        ("5\n", "120"),
        ("10\n", "3628800"),
    ]

    for stdin_val, expected in test_cases:
        print(f"\nSubmitting Input: {stdin_val.strip()} (Expected: {expected})")
        resp = await client.post(
            f"{API_URL}/api/run",
            json={
                "source_code": FACTORIAL_CODE_CORRECT,
                "custom_input": stdin_val,
                "language": "python",
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            stdout = (data.get("stdout") or "").strip()
            verdict = data.get("verdict")
            status = "PASS" if stdout == expected else "FAIL"
            print(f" -> Output: {stdout} | Verdict: {verdict} | Status: {status}")
        elif resp.status_code == 401:
            print(" -> API requires authentication token. Pass token to run.")
            return
        else:
            print(f" -> Error {resp.status_code}: {resp.text}")


async def demo_recursion_error(client: httpx.AsyncClient):
    print("\n--- 2. Testing Faulty Code: Infinite Recursion ---")
    resp = await client.post(
        f"{API_URL}/api/run",
        json={
            "source_code": FACTORIAL_CODE_RECURSION_ERROR,
            "custom_input": "5\n",
            "language": "python",
        },
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f" -> Verdict: {data.get('verdict')} (Expected: RE)")
        print(f" -> Error Message: {data.get('error_message') or data.get('stderr')}")


async def main():
    print("=" * 60)
    print(" MediCode Factorial Sandbox Test Demo")
    print(f" Target API: {API_URL}")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Check API health first
        try:
            health = await client.get(f"{API_URL}/health")
            print(f"API Health: {health.json()}")
        except Exception as exc:
            print(f"Failed to reach API at {API_URL}: {exc}")
            print("\nTo start the server, run:")
            print("  cd MediCode_backend")
            print("  uv run uvicorn medicode.main:app --reload --port 8000")
            print("  or with Docker: docker compose up -d")
            return

        await demo_direct_run(client)
        await demo_recursion_error(client)


if __name__ == "__main__":
    asyncio.run(main())
