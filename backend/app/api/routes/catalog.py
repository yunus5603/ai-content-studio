from fastapi import APIRouter, Depends, HTTPException, status

from app.catalog import CatalogError, get_model, load_catalog, validate_params
from app.catalog.pricing import PLATFORM_FEE, estimate_cost, with_fee
from app.catalog.schema import OPERATION_LABELS
from app.core.config import Settings, get_settings
from app.schemas import EstimateOut, EstimateRequest

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("")
async def catalog(settings: Settings = Depends(get_settings)):
    """Every model we offer, with operations, parameters and prices. Public."""
    models = load_catalog(include_debug=settings.enable_debug_operations).values()
    return {
        "platform_fee": PLATFORM_FEE,
        "operations": OPERATION_LABELS,
        "models": [m.model_dump(exclude={"adapter"}, by_alias=True) for m in models],
    }


@router.post("/estimate", response_model=EstimateOut)
async def estimate(body: EstimateRequest, settings: Settings = Depends(get_settings)):
    try:
        spec = get_model(body.model, include_debug=settings.enable_debug_operations)
        params = validate_params(spec, body.operation, body.params)
    except CatalogError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    cost = estimate_cost(spec, params)
    return EstimateOut(params=params, provider_cost_usd=cost, price_usd=with_fee(cost))
