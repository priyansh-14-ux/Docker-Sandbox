from fastapi import APIRouter

from medicode.api.routes.admin import router as admin_router
from medicode.api.routes.auth import router as auth_router
from medicode.api.routes.courses import router as courses_router
from medicode.api.routes.discussions import router as discussions_router
from medicode.api.routes.enrollments import router as enrollments_router
from medicode.api.routes.labs import router as labs_router
from medicode.api.routes.submissions import router as submissions_router
from medicode.api.routes.users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(courses_router, prefix="/courses", tags=["courses"])
api_router.include_router(enrollments_router, prefix="/courses", tags=["enrollments"])
api_router.include_router(labs_router, prefix="/courses", tags=["labs"])
api_router.include_router(submissions_router, prefix="/submissions", tags=["submissions"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(discussions_router, prefix="/problems", tags=["discussions"])
