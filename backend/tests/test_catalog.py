import pytest

from app.catalog import CatalogError, load_catalog, validate_params
from app.catalog.pricing import cost_from_usage, estimate_cost, with_fee


def test_catalog_loads_and_every_model_prices_its_defaults():
    catalog = load_catalog()
    assert "openai/gpt-image-2.6-sunburst" in catalog
    assert "vertex/veo-3.1-generate-001" in catalog
    assert not any(m.provider == "debug" for m in catalog.values())
    for model in catalog.values():
        for op in model.operations:
            params = validate_params(model, op.operation, {})
            assert estimate_cost(model, params) > 0, (model.id, op.operation)


def test_openai_custom_sizes():
    model = load_catalog()["openai/gpt-image-2.6-sunburst"]
    ok = validate_params(model, "text_to_image", {"size": "1792x1024"})
    assert ok["size"] == "1792x1024"
    for bad in ["1000x1000", "4096x1024", "512x512", "3840x1280x1", "big"]:
        with pytest.raises(CatalogError):
            validate_params(model, "text_to_image", {"size": bad})


def test_conditional_params_and_rules():
    model = load_catalog()["openai/gpt-image-2.6-sunburst"]
    png = validate_params(model, "text_to_image", {})
    assert "frame_count" not in png
    gif = validate_params(model, "text_to_image", {"output_format": "gif"})
    assert gif["frame_count"] == 9
    with pytest.raises(CatalogError, match="GIF frames"):
        validate_params(model, "text_to_image", {"frame_count": 4})
    with pytest.raises(CatalogError, match="one at a time"):
        validate_params(model, "text_to_image", {"output_format": "gif", "n": 2})
    # input_fidelity only applies to edits
    assert "input_fidelity" in validate_params(model, "image_edit", {})
    with pytest.raises(CatalogError):
        validate_params(model, "text_to_image", {"input_fidelity": "high"})


def test_pricing():
    catalog = load_catalog()
    veo = catalog["vertex/veo-3.1-generate-001"]
    p = validate_params(veo, "text_to_video", {"number_of_videos": 2})
    assert estimate_cost(veo, p) == pytest.approx(0.40 * 8 * 2)
    img = catalog["openai/gpt-image-2.6-sunburst"]
    p = validate_params(img, "text_to_image", {"quality": "low", "size": "2048x2048"})
    assert estimate_cost(img, p) == pytest.approx(0.0247 * 4)
    usage = {"text_input_tokens": 100, "image_input_tokens": 0, "output_tokens": 1000}
    assert cost_from_usage(img, usage) == pytest.approx((100 * 5 + 1000 * 30) / 1e6)
    assert with_fee(1.0) == 1.1


async def test_catalog_endpoints(client):
    r = await client.http.get("/v1/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["platform_fee"] == 0.1
    ids = {m["id"] for m in body["models"]}
    assert "debug/pixel" in ids  # debug models on in tests
    assert all("adapter" not in m for m in body["models"])

    r = await client.http.post(
        "/v1/catalog/estimate",
        json={
            "model": "vertex/gemini-3.1-flash-image",
            "operation": "text_to_image",
            "params": {"image_size": "4K", "n": 2},
        },
    )
    assert r.json()["provider_cost_usd"] == pytest.approx(0.302)
    assert r.json()["price_usd"] == pytest.approx(0.3322)
