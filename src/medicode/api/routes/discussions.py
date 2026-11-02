from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from medicode.api.dependencies import get_current_login
from medicode.db.session import get_db_session
from medicode.models.content import Experiment, Lab, Problem, ProblemDiscussion
from medicode.models.identity import Login, Profile, RoleName
from medicode.schemas.discussions import DiscussionCreate, DiscussionEntry, DiscussionThread
from medicode.services.access import require_course_manager, student_has_course_access

router = APIRouter()
ADMIN_ROLES = (RoleName.SUPER_ADMIN, RoleName.INSTITUTE_ADMIN)


@router.get("/{problem_id}/discussions", response_model=list[DiscussionThread])
async def list_problem_discussions(
    problem_id: UUID,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[DiscussionThread]:
    problem, _ = await ensure_problem_access(problem_id, account, session)
    root_rows = await session.execute(
        select(ProblemDiscussion, Profile.full_name)
        .join(Profile, Profile.id == ProblemDiscussion.author_profile_id)
        .where(ProblemDiscussion.problem_id == problem.id, ProblemDiscussion.parent_id.is_(None))
        .order_by(ProblemDiscussion.created_at)
        .offset(offset)
        .limit(limit)
    )
    roots = list(root_rows.all())
    root_ids = [row.id for row, _ in roots]
    reply_rows = (
        await session.execute(
            select(ProblemDiscussion, Profile.full_name)
            .join(Profile, Profile.id == ProblemDiscussion.author_profile_id)
            .where(ProblemDiscussion.parent_id.in_(root_ids))
            .order_by(ProblemDiscussion.created_at)
        )
        if root_ids
        else []
    )

    replies_by_parent: dict[UUID, list[DiscussionEntry]] = {root_id: [] for root_id in root_ids}
    for reply, author_name in reply_rows:
        replies_by_parent[reply.parent_id].append(_entry(reply, author_name))
    return [
        DiscussionThread(
            **_entry(root, author_name).model_dump(),
            replies=replies_by_parent[root.id],
        )
        for root, author_name in roots
    ]


@router.post(
    "/{problem_id}/discussions",
    response_model=DiscussionEntry,
    status_code=status.HTTP_201_CREATED,
)
async def create_problem_discussion(
    problem_id: UUID,
    body: DiscussionCreate,
    account: Annotated[Login, Depends(get_current_login)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DiscussionEntry:
    _problem, profile = await ensure_problem_access(problem_id, account, session)
    clean_body = body.body.strip()
    if not clean_body:
        raise HTTPException(status_code=422, detail="Discussion text cannot be empty")

    if body.parent_id is not None:
        parent = await session.get(ProblemDiscussion, body.parent_id)
        if parent is None or parent.problem_id != problem_id:
            raise HTTPException(status_code=404, detail="Discussion thread not found")
        if parent.parent_id is not None:
            raise HTTPException(status_code=422, detail="Replies must target a top-level post")

    discussion = ProblemDiscussion(
        problem_id=problem_id,
        author_profile_id=profile.id,
        parent_id=body.parent_id,
        body=clean_body,
    )
    session.add(discussion)
    await session.commit()
    await session.refresh(discussion)
    return _entry(discussion, profile.full_name)


async def ensure_problem_access(
    problem_id: UUID, account: Login, session: AsyncSession
) -> tuple[Problem, Profile]:
    problem = await session.get(Problem, problem_id)
    if problem is None or not problem.is_published:
        raise HTTPException(status_code=404, detail="Problem not found")
    experiment = await session.get(Experiment, problem.experiment_id)
    lab = await session.get(Lab, experiment.lab_id) if experiment else None
    if not experiment or not experiment.is_published or not lab or not lab.is_published:
        raise HTTPException(status_code=404, detail="Problem not found")
    if account.profile is None:
        raise HTTPException(status_code=403, detail="A user profile is required")
    role = _role(account)
    if role == RoleName.STUDENT:
        allowed = await student_has_course_access(session, account.profile.id, lab.course_id)
        if not allowed:
            raise HTTPException(status_code=403, detail="Active course enrollment is required")
    elif role == RoleName.FACULTY:
        await require_course_manager(account, lab.course_id, session)
    elif role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Discussion access is not permitted")
    return problem, account.profile


def _entry(row: ProblemDiscussion, author_name: str) -> DiscussionEntry:
    return DiscussionEntry(
        id=row.id,
        parent_id=row.parent_id,
        author_profile_id=row.author_profile_id,
        author_name=author_name,
        body=row.body,
        created_at=row.created_at,
    )


def _role(account: Login) -> RoleName | str | None:
    return account.profile.role.name if account.profile else None
