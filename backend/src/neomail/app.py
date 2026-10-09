"""Application entry points.

* :func:`create_router` returns the product API (``/api/v1``) and the NeoFlow
  action endpoint, for mounting into a host process.
* :func:`create_app` builds the standalone service: the router plus
  ``/healthz``, ``/readyz``, ``/metrics`` and the runtime manifest.
* :data:`app` is the standalone service for ``uvicorn neomail.app:app``.
"""

import logging
from typing import Any

from fastapi import APIRouter, FastAPI, Response
from fastapi.responses import JSONResponse

from neomail import COMPONENT, TITLE, __version__
from neomail.actions import create_actions_router
from neomail.api import create_api_router
from neomail.contracts import (
    MANIFEST_PATH,
    ContractsNotFoundError,
    build_manifest,
    find_contracts_dir,
    load_contracts,
)
from neomail.metrics import PROMETHEUS_MEDIA_TYPE, Metrics, MetricsMiddleware
from neomail.problems import install_problem_handlers, problem
from neomail.settings import Settings, get_settings

logger = logging.getLogger(COMPONENT)


def create_router(settings: Settings | None = None) -> APIRouter:
    """The product's routes, ready to be included in any FastAPI app."""
    router = APIRouter()
    router.include_router(create_api_router())
    router.include_router(create_actions_router(settings))
    return router


def create_app(settings: Settings | None = None) -> FastAPI:
    """The standalone service."""
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(title=TITLE, version=__version__, docs_url="/docs", redoc_url=None)
    app.dependency_overrides[get_settings] = lambda: settings
    install_problem_handlers(app)

    metrics = Metrics()
    app.add_middleware(MetricsMiddleware, metrics=metrics)

    manifest: dict[str, Any] | None = None
    manifest_error: str | None = None
    try:
        contracts = load_contracts(find_contracts_dir(settings))
        manifest = build_manifest(contracts, settings)
    except (ContractsNotFoundError, OSError, ValueError) as exc:
        manifest_error = str(exc)
        logger.error("contracts unavailable: %s", exc)

    app.include_router(create_router(settings))

    @app.get("/healthz", tags=["runtime"], operation_id="healthz")
    async def healthz() -> dict[str, str]:
        """Liveness: the process is up and serving requests."""
        return {"status": "ok"}

    @app.get("/readyz", tags=["runtime"], operation_id="readyz")
    async def readyz() -> Response:
        """Readiness: the core is loaded and the contracts were read."""
        if manifest is None:
            return problem(503, "unavailable", detail=f"contracts unavailable: {manifest_error}")
        return JSONResponse({"status": "ready"})

    @app.get("/metrics", tags=["runtime"], operation_id="metrics")
    async def metrics_endpoint() -> Response:
        return Response(metrics.render(), media_type=PROMETHEUS_MEDIA_TYPE)

    @app.get(MANIFEST_PATH, tags=["runtime"], operation_id="getManifest")
    async def runtime_manifest() -> Response:
        """Types, events, actions and settings schema, harvested by NeoMind and NeoFlow."""
        if manifest is None:
            return problem(503, "unavailable", detail=f"contracts unavailable: {manifest_error}")
        return JSONResponse(manifest)

    return app


app = create_app()
