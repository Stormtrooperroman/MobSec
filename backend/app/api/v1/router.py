from fastapi import APIRouter
from app.api.v1.endpoints import apps
from app.api.v1.endpoints import modules
from app.api.v1.endpoints import chains

api_router = APIRouter()

api_router.include_router(
    apps.router,
    prefix="/apps",
    tags=["Apps"],
    responses={404: {"description": "Not found"}},
)

api_router.include_router(
    modules.router,
    prefix="/modules",
    tags=["Modules"],
    responses={404: {"description": "Not found"}},
)


api_router.include_router(
    chains.router,
    prefix="/chains",
    tags=["Chains"],
    responses={404: {"description": "Not found"}},
)