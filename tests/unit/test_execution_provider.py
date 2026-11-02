import base64
import json
import httpx
import pytest

from medicode.services.execution.judge0 import Judge0Provider
from medicode.services.execution.models import ExecutionLimits, ExecutionRequest
from medicode.services.verdict import Verdict, map_execution_result_to_verdict


def _b64(val: str) -> str:
    return base64.b64encode(val.encode("utf-8")).decode("ascii")


@pytest.mark.asyncio
async def test_judge0_provider_correct_solution() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/submissions/batch" in str(request.url):
            return httpx.Response(201, json=[{"token": "tok-ac-1"}])
        if request.method == "GET" and "/submissions/batch" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "submissions": [
                        {
                            "token": "tok-ac-1",
                            "status_id": 3,
                            "status": {"id": 3, "description": "Accepted"},
                            "stdout": _b64("42\n"),
                            "stderr": None,
                            "time": "0.025",
                            "memory": 12400,
                            "exit_code": 0,
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01, poll_timeout=1.0)

    requests = [
        ExecutionRequest(
            source_code="a, b = map(int, input().split())\nprint(a + b)",
            stdin="20 22\n",
            expected_output="42\n",
        )
    ]
    limits = ExecutionLimits()
    results = await provider.execute_batch(requests, limits)

    assert len(results) == 1
    assert results[0].status_id == 3
    assert results[0].stdout == "42\n"
    assert results[0].time_sec == 0.025

    verdict, err = map_execution_result_to_verdict(results[0], expected_output="42")
    assert verdict == Verdict.AC
    assert err is None


@pytest.mark.asyncio
async def test_judge0_provider_wrong_answer() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-wa-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-wa-1",
                        "status_id": 3,
                        "status": {"id": 3, "description": "Accepted"},
                        "stdout": _b64("99\n"),
                        "time": "0.010",
                        "memory": 10000,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01, poll_timeout=1.0)

    requests = [ExecutionRequest(source_code="print(99)", expected_output="42\n")]
    results = await provider.execute_batch(requests, ExecutionLimits())
    verdict, err = map_execution_result_to_verdict(results[0], expected_output="42")
    assert verdict == Verdict.WA
    assert err == "Output did not match expected output"


@pytest.mark.asyncio
async def test_judge0_provider_syntax_error() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-ce-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-ce-1",
                        "status_id": 6,
                        "status": {"id": 6, "description": "Compilation Error"},
                        "compile_output": _b64("  File 'main.py', line 1\n    def foo(\n            ^\nSyntaxError: was never closed"),
                        "exit_code": 1,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="def foo(")]
    results = await provider.execute_batch(requests, ExecutionLimits())
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=None)
    assert verdict == Verdict.CE
    assert "SyntaxError" in (err or "")


@pytest.mark.asyncio
async def test_judge0_provider_runtime_error() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-re-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-re-1",
                        "status_id": 11,
                        "status": {"id": 11, "description": "Runtime Error (NZEC)"},
                        "stderr": _b64("ZeroDivisionError: division by zero"),
                        "exit_code": 1,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="print(1/0)")]
    results = await provider.execute_batch(requests, ExecutionLimits())
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=None)
    assert verdict == Verdict.RE
    assert "ZeroDivisionError" in (err or "")


@pytest.mark.asyncio
async def test_judge0_provider_infinite_loop_tle() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-tle-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-tle-1",
                        "status_id": 5,
                        "status": {"id": 5, "description": "Time Limit Exceeded"},
                        "time": "1.050",
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="while True: pass")]
    results = await provider.execute_batch(requests, ExecutionLimits(cpu_time_limit_sec=1.0))
    verdict, err = map_execution_result_to_verdict(results[0], expected_output="foo")
    assert verdict == Verdict.TLE
    assert err == "Time Limit Exceeded"


@pytest.mark.asyncio
async def test_judge0_provider_memory_bomb_mle() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-mle-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-mle-1",
                        "status_id": 11,
                        "status": {"id": 11, "description": "Runtime Error (NZEC)"},
                        "stderr": _b64("MemoryError: out of memory"),
                        "memory": 135000,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="x = [0] * 100_000_000")]
    results = await provider.execute_batch(requests, ExecutionLimits(memory_limit_kb=128000))
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=None, memory_limit_kb=128000)
    assert verdict == Verdict.MLE
    assert err == "Memory Limit Exceeded"


@pytest.mark.asyncio
async def test_judge0_provider_fork_bomb() -> None:
    # Fork bombs hit max_processes limit, raising BlockingIOError/OSError
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-fork-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-fork-1",
                        "status_id": 11,
                        "status": {"id": 11, "description": "Runtime Error (NZEC)"},
                        "stderr": _b64("BlockingIOError: [Errno 11] Resource temporarily unavailable"),
                        "exit_code": 1,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="import os\nwhile True: os.fork()")]
    results = await provider.execute_batch(requests, ExecutionLimits(max_processes_and_or_threads=30))
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=None)
    assert verdict == Verdict.RE
    assert "Resource temporarily unavailable" in (err or "")


@pytest.mark.asyncio
async def test_judge0_provider_giant_output_ole() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-ole-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-ole-1",
                        "status_id": 8,
                        "status": {"id": 8, "description": "Output Limit Exceeded"},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="while True: print('A' * 1000)")]
    results = await provider.execute_batch(requests, ExecutionLimits(max_file_size_kb=1024))
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=None)
    assert verdict == Verdict.OLE
    assert err == "Output Limit Exceeded"


@pytest.mark.asyncio
async def test_judge0_provider_network_attempt_blocked() -> None:
    # Sandbox runs with enable_network=false, attempting to connect raises OSError / urllib error
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-net-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-net-1",
                        "status_id": 11,
                        "status": {"id": 11, "description": "Runtime Error (NZEC)"},
                        "stderr": _b64("urllib.error.URLError: <urlopen error [Errno 101] Network is unreachable>"),
                        "exit_code": 1,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="import urllib.request\nurllib.request.urlopen('http://google.com')")]
    results = await provider.execute_batch(requests, ExecutionLimits(enable_network=False))
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=None)
    assert verdict == Verdict.RE
    assert "Network is unreachable" in (err or "")


@pytest.mark.asyncio
async def test_judge0_provider_file_write_outside_tmp_blocked() -> None:
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-file-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-file-1",
                        "status_id": 11,
                        "status": {"id": 11, "description": "Runtime Error (NZEC)"},
                        "stderr": _b64("PermissionError: [Errno 13] Permission denied: '/etc/host_compromise'"),
                        "exit_code": 1,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [ExecutionRequest(source_code="open('/etc/host_compromise', 'w').write('bad')")]
    results = await provider.execute_batch(requests, ExecutionLimits())
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=None)
    assert verdict == Verdict.RE
    assert "Permission denied" in (err or "")


@pytest.mark.asyncio
async def test_judge0_provider_unicode_io() -> None:
    unicode_input = "Hello, 世界 🌍! café & résumé\n"
    unicode_output = "Output: Hello, 世界 🌍! café & résumé\n"

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json=[{"token": "tok-uni-1"}])
        return httpx.Response(
            200,
            json={
                "submissions": [
                    {
                        "token": "tok-uni-1",
                        "status_id": 3,
                        "status": {"id": 3, "description": "Accepted"},
                        "stdout": _b64(unicode_output),
                        "time": "0.015",
                        "memory": 11000,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    provider = Judge0Provider(client=client, poll_interval=0.01)

    requests = [
        ExecutionRequest(
            source_code="s = input()\nprint(f'Output: {s}')",
            stdin=unicode_input,
            expected_output=unicode_output,
        )
    ]
    results = await provider.execute_batch(requests, ExecutionLimits())
    assert results[0].stdout == unicode_output
    verdict, err = map_execution_result_to_verdict(results[0], expected_output=unicode_output)
    assert verdict == Verdict.AC
    assert err is None
