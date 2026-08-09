from fastapi import APIRouter
from app.api.v1.endpoints import apps
from app.api.v1.endpoints import modules
from app.api.v1.endpoints import chains
from app.api.v1.endpoints import settings as settings_endpoints
from app.api.v1.endpoints import external_modules
from app.api.v1.endpoints import dynamic_testing
from app.api.v1.endpoints import emulators

api_router = APIRouter()

api_router.include_router(
    apps.router,
    prefix="/api/v1/apps",
    tags=["Apps"],
    responses={404: {"description": "Not found"}},
)

api_router.include_router(
    modules.router,
    prefix="/api/v1/modules",
    tags=["Modules"],
    responses={404: {"description": "Not found"}},
)

api_router.include_router(
    chains.router,
    prefix="/api/v1/chains",
    tags=["Chains"],
    responses={404: {"description": "Not found"}},
)

api_router.include_router(
    settings_endpoints.router,
    prefix="/api/v1/settings",
    tags=["Settings"],
)

api_router.include_router(
    external_modules.router,
    prefix="/api/v1/external-modules",
    tags=["External Modules"],
    responses={404: {"description": "Not found"}},
)

api_router.include_router(
    dynamic_testing.router, prefix="/api/v1/dynamic-testing", tags=["dynamic-testing"]
)

api_router.include_router(
    emulators.router,
    prefix="/api/v1/emulators",
    tags=["Emulators"],
    responses={404: {"description": "Not found"}},
)
