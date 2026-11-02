from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport

from medicode.api.dependencies import get_current_login
from medicode.db.session import get_db_session
from medicode.main import app
from medicode.models.content import Problem, Submission, SubmissionResult, TestCase
from medicode.models.identity import Login, Profile, Role, RoleName
from medicode.services.execution.base import ExecutionProvider
from medicode.services.execution.factory import get_execution_provider
from medicode.services.execution.models import ExecutionLimits, ExecutionRequest, ExecutionResult
from medicode.services.rate_limiter import _IN_MEMORY_RATE_STORE


class MockExecutionProvider(ExecutionProvider):
    async def execute_batch(
        self, requests: list[ExecutionRequest], limits: ExecutionLimits
    ) -> list[ExecutionResult]:
        results = []
        for r in requests:
            # If code prints sum
            if "a + b" in r.source_code and r.stdin.strip() == "2 3":
                results.append(
                    ExecutionResult(
                        status_id=3,
                        status_description="Accepted",
                        stdout="5\n",
                        time_sec=0.012,
                        memory_kb=10500,
                    )
                )
            else:
                results.append(
                    ExecutionResult(
                        status_id=3,
                        status_description="Accepted",
                        stdout="Output: " + r.stdin,
                        time_sec=0.010,
                        memory_kb=10000,
                    )
                )
        return results

    async def check_health(self) -> bool:
        return True


def create_fake_login(role_name: RoleName, user_id=None, profile_id=None) -> Login:
    u_id = user_id or uuid4()
    p_id = profile_id or uuid4()
    role = Role(id=1 if role_name == RoleName.STUDENT else 2, name=role_name)
    profile = Profile(id=p_id, login_id=u_id, role_id=role.id, full_name="Test User", role=role)
    login = Login(id=u_id, email="test@example.com", is_active=True, profile=profile)
    return login


@pytest.mark.asyncio
async def test_create_submission_queued_202(monkeypatch) -> None:
    monkeypatch.setattr("medicode.api.routes.submissions.enqueue_submission", AsyncMock(return_value=True))
    student = create_fake_login(RoleName.STUDENT)
    problem_id = uuid4()
    fake_problem = Problem(
        id=problem_id,
        experiment_id=None,
        title="Test Problem",
        statement="Solve me",
        is_published=True,
    )

    mock_session = AsyncMock()
    mock_session.add = lambda x: None
    mock_session.get.side_effect = lambda model, id_: fake_problem if model == Problem else None
    mock_session.scalar.return_value = None

    _IN_MEMORY_RATE_STORE.clear()
    app.dependency_overrides[get_current_login] = lambda: student
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/submissions",
                json={
                    "problem_id": str(problem_id),
                    "source_code": "print('hello')",
                    "language": "python",
                },
            )
            assert resp.status_code == 202
            data = resp.json()
            assert "submission_id" in data
            assert data["status"] == "queued"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_submission_validation_oversized_code() -> None:
    student = create_fake_login(RoleName.STUDENT)
    app.dependency_overrides[get_current_login] = lambda: student

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/submissions",
                json={
                    "problem_id": str(uuid4()),
                    "source_code": "a" * 70000,  # > 64 KiB
                    "language": "python",
                },
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_submission_unauthenticated_fails() -> None:
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/submissions",
            json={
                "problem_id": str(uuid4()),
                "source_code": "print('hello')",
                "language": "python",
            },
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_hidden_test_data_leakage_prevention() -> None:
    """Verifies that hidden test case stdout, stderr, and expected outputs are never returned to student."""
    student_profile_id = uuid4()
    student = create_fake_login(RoleName.STUDENT, profile_id=student_profile_id)
    submission_id = uuid4()
    problem_id = uuid4()

    fake_submission = Submission(
        id=submission_id,
        student_profile_id=student_profile_id,
        problem_id=problem_id,
        source_code="print('hello')",
        language="python",
        status="COMPLETED",
        verdict="AC",
        score=Decimal("100.00"),
        created_at=datetime.now(timezone.utc),
    )
    # Visible result
    res_visible = SubmissionResult(
        id=uuid4(),
        submission_id=submission_id,
        test_number=1,
        verdict="AC",
        time_ms=10,
        memory_kb=10000,
        stdout="Visible Stdout Data",
        stderr="",
        is_hidden=False,
    )
    # Hidden result
    res_hidden = SubmissionResult(
        id=uuid4(),
        submission_id=submission_id,
        test_number=2,
        verdict="AC",
        time_ms=12,
        memory_kb=10200,
        stdout="SECRET_HIDDEN_DATA_DO_NOT_LEAK",
        stderr="SECRET_HIDDEN_STDERR",
        is_hidden=True,
    )
    fake_submission.results = [res_visible, res_hidden]

    mock_session = AsyncMock()
    mock_session.scalar.return_value = fake_submission

    app.dependency_overrides[get_current_login] = lambda: student
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/submissions/{submission_id}")
            assert resp.status_code == 200
            data = resp.json()

            results = data["results"]
            assert len(results) == 2

            # Test 1 (Visible): stdout is present
            assert results[0]["is_hidden"] is False
            assert results[0]["stdout"] == "Visible Stdout Data"

            # Test 2 (Hidden): stdout and stderr MUST be None!
            assert results[1]["is_hidden"] is True
            assert results[1]["stdout"] is None
            assert results[1]["stderr"] is None
            assert "SECRET" not in str(data)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_submission_ownership_isolation() -> None:
    """Verifies that Student A cannot access Student B's submission."""
    student_a = create_fake_login(RoleName.STUDENT, profile_id=uuid4())
    student_b_id = uuid4()
    submission_id = uuid4()

    fake_submission = Submission(
        id=submission_id,
        student_profile_id=student_b_id,  # belongs to student B
        problem_id=uuid4(),
        source_code="print('student b')",
        status="COMPLETED",
        created_at=datetime.now(timezone.utc),
    )
    fake_submission.results = []

    mock_session = AsyncMock()
    mock_session.scalar.return_value = fake_submission

    app.dependency_overrides[get_current_login] = lambda: student_a
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/submissions/{submission_id}")
            assert resp.status_code == 403
            assert "You may only view your own submissions" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_run_code_endpoint() -> None:
    student = create_fake_login(RoleName.STUDENT)
    mock_session = AsyncMock()
    mock_provider = MockExecutionProvider()

    app.dependency_overrides[get_current_login] = lambda: student
    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_execution_provider] = lambda: mock_provider

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/run",
                json={
                    "source_code": "a, b = map(int, input().split())\nprint(a + b)",
                    "custom_input": "2 3\n",
                    "language": "python",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
            assert data["verdict"] == "AC"
            assert data["stdout"] == "5\n"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_submission_rate_limiter_blocks_burst(monkeypatch) -> None:
    """Verifies that sending multiple requests faster than the burst limit triggers 429."""
    monkeypatch.setattr("medicode.api.routes.submissions.enqueue_submission", AsyncMock(return_value=True))
    student = create_fake_login(RoleName.STUDENT)
    problem_id = uuid4()
    fake_problem = Problem(id=problem_id, experiment_id=None, title="Test", is_published=True)

    mock_session = AsyncMock()
    mock_session.add = lambda x: None
    mock_session.get.side_effect = lambda model, id_: fake_problem if model == Problem else None
    mock_session.scalar.return_value = None

    _IN_MEMORY_RATE_STORE.clear()
    app.dependency_overrides[get_current_login] = lambda: student
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # First request should pass
            r1 = await client.post(
                "/api/submissions",
                json={"problem_id": str(problem_id), "source_code": "print(1)"},
            )
            assert r1.status_code == 202

            # Immediate second request should hit the burst window limit (1 submission per 3 seconds)
            r2 = await client.post(
                "/api/submissions",
                json={"problem_id": str(problem_id), "source_code": "print(2)"},
            )
            assert r2.status_code == 429
            assert "Too many requests" in r2.json()["detail"]
            assert "Retry-After" in r2.headers
    finally:
        app.dependency_overrides.clear()
        _IN_MEMORY_RATE_STORE.clear()
