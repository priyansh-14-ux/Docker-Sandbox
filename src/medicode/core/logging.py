import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variables for tracing across async execution
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
submission_id_ctx: ContextVar[str | None] = ContextVar("submission_id", default=None)


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON, redacting sensitive fields and omitting source code."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include tracing IDs if present in context or record
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        if req_id:
            data["request_id"] = str(req_id)

        sub_id = getattr(record, "submission_id", None) or submission_id_ctx.get()
        if sub_id:
            data["submission_id"] = str(sub_id)

        # Include structured extra payload if provided
        extra = getattr(record, "extra_payload", None)
        if isinstance(extra, dict):
            # Redact full source code if mistakenly passed at INFO
            cleaned_extra = {}
            for k, v in extra.items():
                if "source_code" in k.lower() or "code" in k.lower():
                    cleaned_extra[k] = f"<redacted_code_len_{len(str(v))}>"
                elif "password" in k.lower() or "token" in k.lower() or "secret" in k.lower():
                    cleaned_extra[k] = "<redacted_secret>"
                else:
                    cleaned_extra[k] = v
            data["extra"] = cleaned_extra

        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)

        return json.dumps(data)


def configure_logging(level: int = logging.INFO) -> None:
    """Configures application-wide structured JSON logging to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to prevent duplicate lines
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)

    # Ensure uvicorn access logs propagate cleanly
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.error").handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Convenience getter for loggers."""
    return logging.getLogger(name)
