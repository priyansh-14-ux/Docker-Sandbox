import math
from enum import StrEnum
from typing import Literal

from medicode.services.execution.models import ExecutionResult


class Verdict(StrEnum):
    AC = "AC"    # Accepted
    WA = "WA"    # Wrong Answer
    TLE = "TLE"  # Time Limit Exceeded
    MLE = "MLE"  # Memory Limit Exceeded
    RE = "RE"    # Runtime Error
    CE = "CE"    # Compilation / Syntax Error
    OLE = "OLE"  # Output Limit Exceeded
    IE = "IE"    # Internal Error / Sandbox Failure


ComparisonMode = Literal["exact", "ignore_whitespace", "float_tolerance"]


def sanitize_output(text: str | None, max_length: int = 2048) -> str | None:
    """Sanitizes and truncates output text to prevent memory bombs and logging bloat."""
    if text is None:
        return None
    if len(text) <= max_length:
        return text
    half = max_length // 2
    return text[:half] + f"\n... [TRUNCATED {len(text) - max_length} CHARACTERS] ...\n" + text[-half:]


def normalize_newlines(text: str) -> str:
    """Normalizes CRLF and CR to standard LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compare_outputs(
    actual: str | None,
    expected: str | None,
    mode: ComparisonMode = "ignore_whitespace",
    float_tolerance: float = 1e-6,
) -> bool:
    """Compares actual stdout against expected output under the specified comparison mode."""
    if actual is None:
        actual = ""
    if expected is None:
        expected = ""

    norm_actual = normalize_newlines(actual)
    norm_expected = normalize_newlines(expected)

    if mode == "exact":
        return norm_actual == norm_expected

    if mode == "ignore_whitespace":
        lines_actual = [line.rstrip() for line in norm_actual.rstrip().split("\n")]
        lines_expected = [line.rstrip() for line in norm_expected.rstrip().split("\n")]
        return lines_actual == lines_expected

    if mode == "float_tolerance":
        tokens_actual = norm_actual.split()
        tokens_expected = norm_expected.split()
        if len(tokens_actual) != len(tokens_expected):
            return False

        for act_tok, exp_tok in zip(tokens_actual, tokens_expected, strict=False):
            try:
                act_val = float(act_tok)
                exp_val = float(exp_tok)
                if not math.isclose(act_val, exp_val, rel_tol=float_tolerance, abs_tol=float_tolerance):
                    return False
            except ValueError:
                if act_tok != exp_tok:
                    return False
        return True

    # Fallback to ignore whitespace
    return norm_actual.strip() == norm_expected.strip()


def map_execution_result_to_verdict(
    result: ExecutionResult,
    expected_output: str | None,
    mode: ComparisonMode = "ignore_whitespace",
    memory_limit_kb: int = 128_000,
) -> tuple[Verdict, str | None]:
    """
    Maps Judge0 execution result and status ID to a MediCode Verdict and error message.
    """
    status_id = result.status_id
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    compile_out = result.compile_output or ""
    message = result.message or ""

    # Status ID 5 = Time Limit Exceeded
    if status_id == 5:
        return Verdict.TLE, "Time Limit Exceeded"

    # Status ID 6 = Compilation Error
    if status_id == 6:
        err = compile_out or stderr or message or "Syntax or compilation error"
        return Verdict.CE, sanitize_output(err)

    # Status ID 8 = Output Limit Exceeded (SIGXFSZ)
    if status_id == 8:
        return Verdict.OLE, "Output Limit Exceeded"

    # Memory limit check or SIGSEGV on excessive memory
    if (result.memory_kb and result.memory_kb >= memory_limit_kb) or (
        "MemoryError" in stderr or "out of memory" in message.lower()
    ):
        return Verdict.MLE, "Memory Limit Exceeded"

    # Status ID 7 (SIGSEGV), 9 (SIGFPE), 10 (SIGABRT), 11 (NZEC), 12 (Other), 14 (Exec Format)
    if status_id in (7, 9, 10, 11, 12, 14):
        err = stderr or message or f"Runtime Error (exit code {result.exit_code})"
        return Verdict.RE, sanitize_output(err)

    # Status ID 13 = Internal Error
    if status_id == 13:
        return Verdict.IE, sanitize_output(message or "Sandbox internal error")

    # Status ID 3 = Accepted by Judge0 or Status ID 4 = Wrong Answer
    # We always verify actual vs expected output using our configured comparison mode
    if expected_output is not None:
        if compare_outputs(stdout, expected_output, mode=mode):
            return Verdict.AC, None
        return Verdict.WA, "Output did not match expected output"

    # If no expected output (e.g. ad-hoc run without expected output), status 3 is AC
    if status_id == 3:
        return Verdict.AC, None

    return Verdict.WA, "Execution finished with unexpected result"


def aggregate_verdicts(
    test_verdicts: list[tuple[Verdict, int | None, int | None]]
) -> tuple[Verdict, int, int, int, int]:
    """
    Aggregates per-test verdicts into overall submission statistics.
    Returns: (overall_verdict, passed_count, total_count, max_time_ms, max_memory_kb)
    """
    if not test_verdicts:
        return Verdict.IE, 0, 0, 0, 0

    total_count = len(test_verdicts)
    passed_count = sum(1 for v, _, _ in test_verdicts if v == Verdict.AC)
    max_time_ms = max((t or 0) for _, t, _ in test_verdicts)
    max_memory_kb = max((m or 0) for _, _, m in test_verdicts)

    # Find first failing verdict
    first_failure = next((v for v, _, _ in test_verdicts if v != Verdict.AC), None)
    overall_verdict = Verdict.AC if first_failure is None else first_failure

    return overall_verdict, passed_count, total_count, max_time_ms, max_memory_kb
