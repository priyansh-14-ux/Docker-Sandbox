import os
import httpx
import pytest

from medicode.services.execution.judge0 import Judge0Provider
from medicode.services.execution.models import ExecutionLimits, ExecutionRequest
from medicode.services.verdict import Verdict, map_execution_result_to_verdict

JUDGE0_LIVE_URL = os.getenv("JUDGE0_URL", "http://localhost:2358")
JUDGE0_AUTH_TOKEN = os.getenv("JUDGE0_AUTH_TOKEN", "medicode-judge0-secret-token")


async def is_judge0_live() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                f"{JUDGE0_LIVE_URL}/about",
                headers={"X-Auth-Token": JUDGE0_AUTH_TOKEN},
            )
            return resp.status_code == 200
    except Exception:
        return False


@pytest.mark.asyncio
async def test_live_judge0_python_execution() -> None:
    live = await is_judge0_live()
    if not live:
        pytest.skip("Live Judge0 container is not reachable at " + JUDGE0_LIVE_URL)

    async with httpx.AsyncClient(timeout=15.0) as client:
        provider = Judge0Provider(
            client=client,
            base_url=JUDGE0_LIVE_URL,
            auth_header="X-Auth-Token",
            auth_token=JUDGE0_AUTH_TOKEN,
            default_language_id=71,
        )

        requests = [
            ExecutionRequest(
                source_code="import sys\nprint('Hello from Live Judge0 Sandbox!')",
                stdin="",
                expected_output="Hello from Live Judge0 Sandbox!\n",
            )
        ]
        limits = ExecutionLimits(
            cpu_time_limit_sec=1.0,
            wall_time_limit_sec=3.0,
            memory_limit_kb=128000,
            enable_network=False,
        )

        results = await provider.execute_batch(requests, limits)
        assert len(results) == 1
        assert results[0].status_id == 3
        assert "Hello from Live Judge0 Sandbox!" in (results[0].stdout or "")

        verdict, err = map_execution_result_to_verdict(results[0], expected_output="Hello from Live Judge0 Sandbox!\n")
        assert verdict == Verdict.AC
        assert err is None
