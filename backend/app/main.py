from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.cloud_regions import router as cloud_regions_router
from app.api.routes.monitor import router as monitor_router
from app.api.routes.optimization import router as optimization_router
from app.api.routes.scheduling import router as scheduling_router
from app.api.routes.workloads import router as workloads_router
from app.services.cloud_regions import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database()
    yield


app = FastAPI(
    title="GreenScale AI",
    description="Carbon-aware multi-cloud workload optimization API.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(cloud_regions_router)
app.include_router(workloads_router)
app.include_router(optimization_router)
app.include_router(scheduling_router)
app.include_router(monitor_router)


@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {
        "project": "GreenScale AI",
        "status": "running",
        "message": "Carbon-aware cloud optimization API is ready.",
    }


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "greenscale-backend", "version": "0.1.0"}
