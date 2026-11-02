import asyncio
import base64
import time
from typing import Any

import httpx

from medicode.core.logging import get_logger
from medicode.services.execution.base import ExecutionProvider
from medicode.services.execution.models import ExecutionLimits, ExecutionRequest, ExecutionResult

logger = get_logger(__name__)

# Judge0 status constants
STATUS_IN_QUEUE = 1
STATUS_PROCESSING = 2
STATUS_ACCEPTED = 3
STATUS_WRONG_ANSWER = 4
STATUS_TIME_LIMIT_EXCEEDED = 5
STATUS_COMPILATION_ERROR = 6
STATUS_RUNTIME_ERROR_SIGSEGV = 7
STATUS_RUNTIME_ERROR_SIGXFSZ = 8
STATUS_RUNTIME_ERROR_SIGFPE = 9
STATUS_RUNTIME_ERROR_SIGABRT = 10
STATUS_RUNTIME_ERROR_NZEC = 11
STATUS_RUNTIME_ERROR_OTHER = 12
STATUS_INTERNAL_ERROR = 13
STATUS_EXEC_FORMAT_ERROR = 14


def _b64_encode(text: str | None) -> str | None:
    if text is None:
        return None
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _b64_decode(data: str | None) -> str | None:
    if not data:
        return None
    try:
        return base64.b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return data


class Judge0Provider(ExecutionProvider):
    """Judge0 CE / RapidAPI implementation of the ExecutionProvider."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "http://localhost:2358",
        auth_header: str | None = "X-Auth-Token",
        auth_token: str | None = None,
        is_rapidapi: bool = False,
        rapidapi_host: str = "judge0-ce.p.rapidapi.com",
        poll_interval: float = 0.1,
        poll_timeout: float = 15.0,
        default_language_id: int = 71,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header
        self.auth_token = auth_token
        self.is_rapidapi = is_rapidapi
        self.rapidapi_host = rapidapi_host
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.default_language_id = default_language_id

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.is_rapidapi:
            if self.auth_token:
                headers["X-RapidAPI-Key"] = self.auth_token
            if self.rapidapi_host:
                headers["X-RapidAPI-Host"] = self.rapidapi_host
        elif self.auth_header and self.auth_token:
            headers[self.auth_header] = self.auth_token
        return headers

    async def execute_batch(
        self, requests: list[ExecutionRequest], limits: ExecutionLimits
    ) -> list[ExecutionResult]:
        if not requests:
            return []

        payload_submissions = []
        for req in requests:
            item: dict[str, Any] = {
                "language_id": req.language_id or self.default_language_id,
                "source_code": _b64_encode(req.source_code),
                "stdin": _b64_encode(req.stdin),
                "cpu_time_limit": limits.cpu_time_limit_sec,
                "wall_time_limit": limits.wall_time_limit_sec,
                "memory_limit": limits.memory_limit_kb,
                "stack_limit": limits.stack_limit_kb,
                "max_processes_and_or_threads": limits.max_processes_and_or_threads,
                "max_file_size": limits.max_file_size_kb,
                "enable_network": limits.enable_network,
                "number_of_runs": limits.number_of_runs,
            }
            if req.expected_output is not None:
                item["expected_output"] = _b64_encode(req.expected_output)
            payload_submissions.append(item)

        url = f"{self.base_url}/submissions/batch?base64_encoded=true"
        headers = self._build_headers()

        try:
            post_resp = await self.client.post(
                url, json={"submissions": payload_submissions}, headers=headers, timeout=10.0
            )
            post_resp.raise_for_status()
            token_list = post_resp.json()
        except httpx.HTTPError as exc:
            logger.error("Failed to post batch submissions to Judge0: %s", str(exc))
            return [
                ExecutionResult(
                    status_id=STATUS_INTERNAL_ERROR,
                    status_description="Internal Error: Failed to dispatch to execution sandbox",
                    message=f"Sandbox unreachable: {exc.__class__.__name__}",
                )
                for _ in requests
            ]

        # Extract tokens
        tokens = [item["token"] for item in token_list if "token" in item]
        if not tokens or len(tokens) != len(requests):
            logger.error("Mismatch in Judge0 batch tokens returned: %s", token_list)
            return [
                ExecutionResult(
                    status_id=STATUS_INTERNAL_ERROR,
                    status_description="Internal Error: Invalid token response from sandbox",
                )
                for _ in requests
            ]

        # Poll for completion with exponential backoff starting at poll_interval
        tokens_param = ",".join(tokens)
        poll_url = (
            f"{self.base_url}/submissions/batch?"
            f"tokens={tokens_param}&base64_encoded=true&"
            f"fields=token,status_id,status,stdout,stderr,compile_output,message,time,memory,exit_code,exit_signal"
        )

        start_time = time.monotonic()
        current_sleep = self.poll_interval
        results_map: dict[str, ExecutionResult] = {}

        while time.monotonic() - start_time < self.poll_timeout:
            await asyncio.sleep(current_sleep)
            current_sleep = min(current_sleep * 1.5, 0.5)

            try:
                poll_resp = await self.client.get(poll_url, headers=headers, timeout=5.0)
                poll_resp.raise_for_status()
                poll_data = poll_resp.json()
                raw_submissions = poll_data.get("submissions", [])
            except httpx.HTTPError as exc:
                logger.warning("Transient error during Judge0 poll: %s", str(exc))
                continue

            all_done = True
            for item in raw_submissions:
                token = item.get("token")
                status_id = item.get("status_id") or (item.get("status", {}).get("id"))
                if not status_id or status_id in (STATUS_IN_QUEUE, STATUS_PROCESSING):
                    all_done = False
                elif token:
                    status_desc = (item.get("status", {}).get("description")) or "Completed"
                    time_sec = float(item["time"]) if item.get("time") is not None else None
                    memory_kb = int(item["memory"]) if item.get("memory") is not None else None
                    results_map[token] = ExecutionResult(
                        status_id=status_id,
                        status_description=status_desc,
                        stdout=_b64_decode(item.get("stdout")),
                        stderr=_b64_decode(item.get("stderr")),
                        compile_output=_b64_decode(item.get("compile_output")),
                        message=_b64_decode(item.get("message")),
                        time_sec=time_sec,
                        memory_kb=memory_kb,
                        exit_code=item.get("exit_code"),
                        exit_signal=item.get("exit_signal"),
                        token=token,
                    )

            if all_done and len(results_map) == len(tokens):
                break

        # Assemble final ordered results
        ordered_results: list[ExecutionResult] = []
        for token in tokens:
            if token in results_map:
                ordered_results.append(results_map[token])
            else:
                ordered_results.append(
                    ExecutionResult(
                        status_id=STATUS_INTERNAL_ERROR,
                        status_description="Internal Error: Execution timed out while waiting in sandbox",
                        token=token,
                    )
                )

        return ordered_results

    async def check_health(self) -> bool:
        url = f"{self.base_url}/about"
        headers = self._build_headers()
        try:
            resp = await self.client.get(url, headers=headers, timeout=3.0)
            return resp.status_code == 200
        except Exception:
            # Fallback to /system_info or /languages
            try:
                resp = await self.client.get(f"{self.base_url}/system_info", headers=headers, timeout=3.0)
                return resp.status_code == 200
            except Exception:
                return False
