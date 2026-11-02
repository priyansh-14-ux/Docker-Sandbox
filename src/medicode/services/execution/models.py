from pydantic import BaseModel, Field


class ExecutionRequest(BaseModel):
    source_code: str
    stdin: str = ""
    expected_output: str | None = None
    language_id: int | None = None


class ExecutionLimits(BaseModel):
    cpu_time_limit_sec: float = 1.0
    wall_time_limit_sec: float = 3.0
    memory_limit_kb: int = 128_000
    stack_limit_kb: int = 64_000
    max_processes_and_or_threads: int = 30
    max_file_size_kb: int = 1024
    enable_network: bool = False
    number_of_runs: int = 1


class ExecutionResult(BaseModel):
    status_id: int
    status_description: str
    stdout: str | None = None
    stderr: str | None = None
    compile_output: str | None = None
    message: str | None = None
    time_sec: float | None = None
    memory_kb: int | None = None
    exit_code: int | None = None
    exit_signal: int | None = None
    token: str | None = None
