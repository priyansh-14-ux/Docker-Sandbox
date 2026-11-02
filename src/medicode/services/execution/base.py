from abc import ABC, abstractmethod

from medicode.services.execution.models import ExecutionLimits, ExecutionRequest, ExecutionResult


class ExecutionProvider(ABC):
    """Abstract execution provider for running untrusted student code."""

    @abstractmethod
    async def execute_batch(
        self, requests: list[ExecutionRequest], limits: ExecutionLimits
    ) -> list[ExecutionResult]:
        """Execute a batch of test cases against the sandbox engine."""
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """Check whether the execution backend is healthy and responding."""
        pass
