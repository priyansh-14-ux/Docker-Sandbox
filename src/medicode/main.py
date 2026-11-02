from fastapi import FastAPI

from medicode.api.router import api_router
from medicode.api.routes.realtime import router as realtime_router

app = FastAPI(
    title="MediCode API",
    version="0.1.0",
    description="Backend API for the MediCode educational coding platform.",
)

app.include_router(api_router, prefix="/api")
app.include_router(realtime_router, prefix="/ws", tags=["realtime"])


@app.get("/", tags=["system"])
async def read_root() -> dict[str, str]:
    return {"message": "Welcome to MediCode API"}


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
