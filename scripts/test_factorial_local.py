#!/usr/bin/env python3
"""
MediCode Factorial Problem Local Test (No Docker Required)
Demonstrates the full judging pipeline, output comparisons, verdict assignment,
and hidden test masking directly in your terminal.
"""

import math
import time
from uuid import uuid4

from medicode.services.execution.models import ExecutionLimits, ExecutionRequest, ExecutionResult
from medicode.services.verdict import (
    Verdict,
    aggregate_verdicts,
    map_execution_result_to_verdict,
    sanitize_output,
)

# Test cases for Factorial (2 visible, 3 hidden)
TEST_CASES = [
    {"num": 1, "input": "0\n", "expected": "1\n", "is_hidden": False, "points": 20},
    {"num": 2, "input": "5\n", "expected": "120\n", "is_hidden": False, "points": 20},
    {"num": 3, "input": "1\n", "expected": "1\n", "is_hidden": True, "points": 20},
    {"num": 4, "input": "10\n", "expected": "3628800\n", "is_hidden": True, "points": 20},
    {"num": 5, "input": "15\n", "expected": "1307674368000\n", "is_hidden": True, "points": 20},
]


def run_code_simulation(code_type: str, stdin: str) -> ExecutionResult:
    """Simulates code execution outputs for demonstration."""
    n = int(stdin.strip())
    if code_type == "correct":
        ans = math.factorial(n)
        return ExecutionResult(
            status_id=3,
            status_description="Accepted",
            stdout=f"{ans}\n",
            time_sec=0.015,
            memory_kb=11400,
        )
    elif code_type == "recursion_error":
        return ExecutionResult(
            status_id=11,
            status_description="Runtime Error (NZEC)",
            stderr="RecursionError: maximum recursion depth exceeded while calling a Python object\n",
            exit_code=1,
            time_sec=0.045,
            memory_kb=18000,
        )
    elif code_type == "wrong_answer":
        return ExecutionResult(
            status_id=3,
            status_description="Accepted",
            stdout=f"{n * 2}\n",
            time_sec=0.010,
            memory_kb=10500,
        )
    elif code_type == "infinite_loop":
        return ExecutionResult(
            status_id=5,
            status_description="Time Limit Exceeded",
            time_sec=1.050,
            memory_kb=12000,
        )
    raise ValueError(f"Unknown code_type {code_type}")


def test_submission(submission_title: str, code_type: str):
    print("\n" + "=" * 65)
    print(f" SUBMISSION EVALUATION: {submission_title}")
    print("=" * 65)

    verdicts_summary = []
    earned_points = 0
    total_points = sum(tc["points"] for tc in TEST_CASES)

    print(f"{'Test':<6} | {'Input':<6} | {'Expected':<14} | {'Status':<8} | {'Verdict':<8} | {'Student View':<20}")
    print("-" * 75)

    for tc in TEST_CASES:
        sim_result = run_code_simulation(code_type, tc["input"])
        verdict, err = map_execution_result_to_verdict(
            sim_result, tc["expected"], mode="ignore_whitespace"
        )
        time_ms = int(sim_result.time_sec * 1000) if sim_result.time_sec else None
        memory_kb = sim_result.memory_kb
        verdicts_summary.append((verdict, time_ms, memory_kb))

        if verdict == Verdict.AC:
            earned_points += tc["points"]

        # Student view: if hidden, stdout is strictly masked!
        if tc["is_hidden"]:
            student_output = "[MASKED - HIDDEN TEST]"
        else:
            student_output = f"stdout: {(sim_result.stdout or '').strip()}"

        print(
            f"#{tc['num']:<5} | "
            f"{tc['input'].strip():<6} | "
            f"{tc['expected'].strip()[:12]:<14} | "
            f"{('HIDDEN' if tc['is_hidden'] else 'SAMPLE'):<8} | "
            f"{verdict.value:<8} | "
            f"{student_output:<20}"
        )

    overall, passed_cnt, total_cnt, max_t, max_m = aggregate_verdicts(verdicts_summary)
    score = (earned_points / total_points) * 100

    print("-" * 75)
    print(f"OVERALL VERDICT : {overall.value}")
    print(f"TESTS PASSED    : {passed_cnt}/{total_cnt}")
    print(f"FINAL SCORE     : {score:.1f}%")
    print(f"MAX RUNTIME     : {max_t} ms")
    print(f"MAX MEMORY      : {max_m} KB")
    print("=" * 65)


def main():
    print("=================================================================")
    print("  Project MediCode: Code-Execution Sandbox Evaluation Demo       ")
    print("  Problem Statement: Factorial of a Number                       ")
    print("=================================================================")

    # 1. Correct Factorial Implementation
    test_submission("Correct Solution (math.factorial)", "correct")

    # 2. Infinite Recursion Bug
    test_submission("Faulty Solution (Recursion depth exceeded)", "recursion_error")

    # 3. Wrong Answer
    test_submission("Faulty Solution (Off-by-one / Wrong Formula)", "wrong_answer")

    # 4. Infinite Loop Timeout
    test_submission("Hostile Solution (Infinite Loop TLE)", "infinite_loop")


if __name__ == "__main__":
    main()
