import httpx
from fastapi import Depends

from medicode.core.config import Settings, get_settings
from medicode.services.execution.base import ExecutionProvider
from medicode.services.execution.judge0 import Judge0Provider

# Global client holder managed during lifespan
_GLOBAL_HTTP_CLIENT: httpx.AsyncClient | None = None


def set_global_http_client(client: httpx.AsyncClient) -> None:
    global _GLOBAL_HTTP_CLIENT
    _GLOBAL_HTTP_CLIENT = client


def get_http_client() -> httpx.AsyncClient:
    global _GLOBAL_HTTP_CLIENT
    if _GLOBAL_HTTP_CLIENT is None or _GLOBAL_HTTP_CLIENT.is_closed:
        _GLOBAL_HTTP_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _GLOBAL_HTTP_CLIENT


def get_execution_provider(
    client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> ExecutionProvider:
    """Factory dependency returning the configured execution provider."""
    if settings.execution_provider == "judge0_rapidapi":
        return Judge0Provider(
            client=client,
            base_url="https://judge0-ce.p.rapidapi.com",
            auth_token=settings.judge0_rapidapi_key,
            is_rapidapi=True,
            rapidapi_host=settings.judge0_rapidapi_host,
            poll_interval=settings.judge0_poll_interval_sec,
            poll_timeout=settings.judge0_poll_timeout_sec,
            default_language_id=settings.python_language_id,
        )

    return Judge0Provider(
        client=client,
        base_url=settings.judge0_url,
        auth_header=settings.judge0_auth_header,
        auth_token=settings.judge0_auth_token,
        is_rapidapi=False,
        poll_interval=settings.judge0_poll_interval_sec,
        poll_timeout=settings.judge0_poll_timeout_sec,
        default_language_id=settings.python_language_id,
    )
