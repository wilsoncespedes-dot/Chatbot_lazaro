"""Fase 5: ruta pública de los gráficos temporales con enlace firmado."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .charts import CHART_MEDIA_PREFIX, chart_link_valid
from .config import Settings
from .domain import Adapters


def create_charts_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()

    @router.get(CHART_MEDIA_PREFIX + "{name}")
    async def chart_media(name: str, exp: str = "", sig: str = "") -> Response:
        # Firma inválida, vencida o gráfico inexistente responden igual (404):
        # no se revela si el id existió.
        chart_id = name[:-4] if name.endswith(".png") else ""
        now = adapters.clock()
        if not settings.charts_enabled or not chart_link_valid(
            chart_id, exp, sig, settings.chart_link_signing_key.strip(), now
        ):
            raise HTTPException(status_code=404, detail="not_found")
        png = adapters.repository.get_chart_image(chart_id, now)
        if png is None:
            raise HTTPException(status_code=404, detail="not_found")
        return Response(
            content=png,
            media_type="image/png",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=300",
                "Referrer-Policy": "no-referrer",
            },
        )

    return router
