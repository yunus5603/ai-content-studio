"""Model catalog: every model we offer, its operations, parameters and prices.

The catalog lives in models.yaml so models can be added, retired or re-priced
without touching code. The API serves it to the UI, which builds its controls
from it, and every job is validated against it.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.catalog.schema import ModelSpec, ParamSpec

CATALOG_PATH = Path(__file__).with_name("models.yaml")


class CatalogError(ValueError):
    pass


@lru_cache
def load_catalog(
    include_debug: bool = False, include_internal: bool = False
) -> dict[str, ModelSpec]:
    """Models users can pick. `include_internal` adds studio-side steps (e.g. stitching
    storyboard clips) that features submit as jobs but the model picker never shows."""
    raw = yaml.safe_load(CATALOG_PATH.read_text())
    models = [ModelSpec.model_validate(m) for m in raw["models"]]
    if include_debug:
        models += [ModelSpec.model_validate(m) for m in raw.get("debug_models", [])]
    if include_internal:
        models += [ModelSpec.model_validate(m) for m in raw.get("internal_models", [])]
    return {m.id: m for m in models if m.enabled}


def get_model(
    model_id: str, include_debug: bool = False, include_internal: bool = False
) -> ModelSpec:
    model = load_catalog(include_debug, include_internal).get(model_id)
    if model is None:
        raise CatalogError(f"Unknown model: {model_id}")
    return model


def _check_size(spec: ParamSpec, value: Any) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{spec.label}: expected WIDTHxHEIGHT")
    if value in {o.value for o in spec.options}:
        return value
    rules = spec.size_rules
    if not rules:
        raise CatalogError(f"{spec.label}: choose one of the listed sizes")
    try:
        w, h = (int(x) for x in value.lower().split("x"))
    except ValueError as exc:
        raise CatalogError(f"{spec.label}: expected WIDTHxHEIGHT") from exc
    multiple = int(rules.get("multiple", 1))
    if w % multiple or h % multiple:
        raise CatalogError(f"{spec.label}: width and height must be multiples of {multiple}")
    if max(w, h) > rules.get("max_edge", 1e9):
        raise CatalogError(f"{spec.label}: longest edge is {int(rules['max_edge'])}px")
    if max(w, h) / min(w, h) > rules.get("max_ratio", 1e9):
        raise CatalogError(f"{spec.label}: aspect ratio can't exceed {rules['max_ratio']}:1")
    pixels = w * h
    if not rules.get("min_pixels", 0) <= pixels <= rules.get("max_pixels", 1e12):
        raise CatalogError(f"{spec.label}: total pixels out of range")
    return f"{w}x{h}"


def _coerce(spec: ParamSpec, value: Any) -> Any:
    if spec.type == "enum":
        allowed = [o.value for o in spec.options]
        if value not in allowed:
            raise CatalogError(f"{spec.label}: must be one of {allowed}")
        return value
    if spec.type == "bool":
        if not isinstance(value, bool):
            raise CatalogError(f"{spec.label}: must be true or false")
        return value
    if spec.type in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise CatalogError(f"{spec.label}: must be a number")
        if spec.type == "int":
            if int(value) != value:
                raise CatalogError(f"{spec.label}: must be a whole number")
            value = int(value)
        if spec.min is not None and value < spec.min:
            raise CatalogError(f"{spec.label}: minimum is {spec.min:g}")
        if spec.max is not None and value > spec.max:
            raise CatalogError(f"{spec.label}: maximum is {spec.max:g}")
        return value
    if spec.type == "text":
        if not isinstance(value, str):
            raise CatalogError(f"{spec.label}: must be text")
        if spec.max is not None and len(value) > spec.max:
            raise CatalogError(f"{spec.label}: too long")
        return value
    if spec.type == "size":
        return _check_size(spec, value)
    raise CatalogError(f"Unsupported parameter type {spec.type}")


def _active(spec: ParamSpec, params: dict[str, Any]) -> bool:
    return all(params.get(k) in vals for k, vals in spec.when.items())


def validate_params(model: ModelSpec, operation: str, params: dict[str, Any]) -> dict[str, Any]:
    """Return params with defaults filled in and values checked; raise CatalogError if invalid."""
    if model.operation(operation) is None:
        raise CatalogError(f"{model.name} does not support {operation.replace('_', ' ')}")
    specs = model.params_for(operation)
    known = {s.name for s in specs}
    unknown = set(params) - known
    if unknown:
        raise CatalogError(f"{model.name} doesn't accept: {', '.join(sorted(unknown))}")

    out: dict[str, Any] = {}
    # Two passes so `when` conditions see the final values of the params they depend on.
    for spec in specs:
        value = params.get(spec.name, spec.default)
        if value is not None:
            out[spec.name] = _coerce(spec, value)
    for spec in specs:
        if spec.name in out and not _active(spec, out):
            if spec.name in params:
                raise CatalogError(f"{spec.label} isn't available with these settings")
            out.pop(spec.name)

    for rule in model.rules:
        if all(out.get(k) in v for k, v in rule.if_.items()):
            for k, allowed in rule.then.items():
                if k in out and out[k] not in allowed:
                    raise CatalogError(rule.message)
    return out
