import pytest

from medicode.services.execution.models import ExecutionResult
from medicode.services.verdict import (
    Verdict,
    aggregate_verdicts,
    compare_outputs,
    map_execution_result_to_verdict,
    normalize_newlines,
    sanitize_output,
)


def test_normalize_newlines() -> None:
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


def test_compare_outputs_exact() -> None:
    assert compare_outputs("hello\n", "hello\n", mode="exact")
    assert not compare_outputs("hello \n", "hello\n", mode="exact")


def test_compare_outputs_ignore_whitespace() -> None:
    # Trailing whitespace on lines and trailing empty lines ignored
    assert compare_outputs("hello   \r\nworld  \n\n", "hello\nworld", mode="ignore_whitespace")
    assert not compare_outputs("hello world", "world hello", mode="ignore_whitespace")


def test_compare_outputs_float_tolerance() -> None:
    assert compare_outputs("3.14159265", "3.14159260", mode="float_tolerance", float_tolerance=1e-5)
    assert not compare_outputs("3.14159", "3.14200", mode="float_tolerance", float_tolerance=1e-5)
    # Mixed tokens
    assert compare_outputs("Result: 42.0000001", "Result: 42.0", mode="float_tolerance", float_tolerance=1e-4)


def test_sanitize_output_truncation() -> None:
    short_text = "abc" * 10
    assert sanitize_output(short_text, max_length=100) == short_text

    long_text = "X" * 5000
    sanitized = sanitize_output(long_text, max_length=100)
    assert sanitized is not None
    assert len(sanitized) < 300
    assert "[TRUNCATED" in sanitized


def test_map_execution_result_accepted() -> None:
    result = ExecutionResult(
        status_id=3,
        status_description="Accepted",
        stdout="42\n",
        time_sec=0.015,
        memory_kb=12000,
    )
    verdict, err = map_execution_result_to_verdict(result, expected_output="42")
    assert verdict == Verdict.AC
    assert err is None


def test_map_execution_result_wrong_answer() -> None:
    result = ExecutionResult(
        status_id=3,
        status_description="Accepted",
        stdout="41\n",
        time_sec=0.015,
        memory_kb=12000,
    )
    verdict, err = map_execution_result_to_verdict(result, expected_output="42")
    assert verdict == Verdict.WA
    assert err == "Output did not match expected output"


def test_map_execution_result_tle() -> None:
    result = ExecutionResult(
        status_id=5,
        status_description="Time Limit Exceeded",
        time_sec=1.05,
    )
    verdict, err = map_execution_result_to_verdict(result, expected_output="42")
    assert verdict == Verdict.TLE
    assert err == "Time Limit Exceeded"


def test_map_execution_result_mle() -> None:
    result = ExecutionResult(
        status_id=11,
        status_description="Runtime Error (NZEC)",
        stderr="MemoryError: unable to allocate array",
        memory_kb=130000,
    )
    verdict, err = map_execution_result_to_verdict(result, expected_output="42", memory_limit_kb=128000)
    assert verdict == Verdict.MLE
    assert err == "Memory Limit Exceeded"


def test_map_execution_result_ce() -> None:
    result = ExecutionResult(
        status_id=6,
        status_description="Compilation Error",
        compile_output="SyntaxError: invalid syntax",
    )
    verdict, err = map_execution_result_to_verdict(result, expected_output="42")
    assert verdict == Verdict.CE
    assert "SyntaxError" in (err or "")


def test_map_execution_result_ole() -> None:
    result = ExecutionResult(
        status_id=8,
        status_description="Output Limit Exceeded",
    )
    verdict, err = map_execution_result_to_verdict(result, expected_output="42")
    assert verdict == Verdict.OLE
    assert err == "Output Limit Exceeded"


def test_aggregate_verdicts() -> None:
    results = [
        (Verdict.AC, 15, 12000),
        (Verdict.AC, 25, 15000),
        (Verdict.WA, 10, 11000),
        (Verdict.AC, 30, 14000),
    ]
    overall, passed_cnt, total_cnt, max_t, max_m = aggregate_verdicts(results)
    assert overall == Verdict.WA
    assert passed_cnt == 3
    assert total_cnt == 4
    assert max_t == 30
    assert max_m == 15000


def test_aggregate_verdicts_all_accepted() -> None:
    results = [
        (Verdict.AC, 10, 8000),
        (Verdict.AC, 20, 9000),
    ]
    overall, passed_cnt, total_cnt, max_t, max_m = aggregate_verdicts(results)
    assert overall == Verdict.AC
    assert passed_cnt == 2
    assert total_cnt == 2
