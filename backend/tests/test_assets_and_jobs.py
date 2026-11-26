import httpx

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.providers.debug import PIXEL as _PIXEL
from app.services.storage import get_storage
from app.worker.runner import claim_next, run_job


async def _personal(user):
    return (await user.get("/v1/me")).json()["workspaces"][0]["id"]


async def _drain():
    while job := await claim_next(SessionLocal):
        await run_job(job, SessionLocal, get_storage(), get_settings())


async def test_upload_list_and_fetch(alice, client):
    ws = await _personal(alice)
    r = await alice.post(
        f"/v1/workspaces/{ws}/uploads", files={"file": ("pic.png", _PIXEL, "image/png")}
    )
    assert r.status_code == 201, r.text
    asset = r.json()
    assert asset["media_type"] == "image" and asset["content_type"] == "image/png"

    page = (await alice.get(f"/v1/workspaces/{ws}/assets")).json()
    assert [a["id"] for a in page["items"]] == [asset["id"]]

    url = httpx.URL(asset["url"])
    got = await client.http.get(url.path, params=dict(url.params))
    assert got.status_code == 200 and got.content == _PIXEL
    bad = await client.http.get(url.path, params={**dict(url.params), "sig": "nope"})
    assert bad.status_code == 403


async def test_upload_rejects_disguised_files(alice):
    ws = await _personal(alice)
    r = await alice.post(
        f"/v1/workspaces/{ws}/uploads",
        files={"file": ("evil.png", b"<script>alert(1)</script>", "image/png")},
    )
    assert r.status_code == 415


def _job(**overrides):
    body = {"operation": "text_to_image", "model": "debug/pixel", "prompt": "a cat"}
    body.update(overrides)
    return body


async def test_job_lifecycle(alice):
    ws = await _personal(alice)
    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job(params={"n": 2}))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["status"] == "queued"
    assert created["estimated_cost_usd"] == 0.02
    assert created["estimated_price_usd"] == 0.022  # +10% platform fee
    assert created["params"] == {"n": 2, "placeholder": False, "fail": False}  # defaults filled in

    await _drain()
    job = (await alice.get(f"/v1/workspaces/{ws}/jobs/{created['id']}")).json()
    assert job["status"] == "succeeded" and job["progress"] == 1.0
    assert job["cost_usd"] == 0.02
    assert len(job["outputs"]) == 2
    outputs = (await alice.get(f"/v1/workspaces/{ws}/assets?kind=output")).json()["items"]
    assert len(outputs) == 2  # saved to the gallery automatically


async def test_failed_job_records_error(alice):
    ws = await _personal(alice)
    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job(params={"fail": True}))
    await _drain()
    job = (await alice.get(f"/v1/workspaces/{ws}/jobs/{r.json()['id']}")).json()
    assert job["status"] == "failed" and job["error"] == "Debug failure requested"


async def test_invalid_requests_rejected(alice, bob):
    ws = await _personal(alice)
    url = f"/v1/workspaces/{ws}/jobs"
    assert (await alice.post(url, json=_job(model="openai/nope"))).status_code == 422
    assert (await alice.post(url, json=_job(operation="text_to_video"))).status_code == 422
    assert (await alice.post(url, json=_job(params={"n": 99}))).status_code == 422
    assert (await alice.post(url, json=_job(params={"bogus": 1}))).status_code == 422
    assert (await alice.post(url, json=_job(prompt=""))).status_code == 422

    # Edit needs a reference image, and it must be from this workspace.
    r = await alice.post(url, json=_job(operation="image_edit"))
    assert r.status_code == 422 and "Reference images" in r.json()["detail"]
    bob_ws = await _personal(bob)
    up = (
        await bob.post(
            f"/v1/workspaces/{bob_ws}/uploads", files={"file": ("p.png", _PIXEL, "image/png")}
        )
    ).json()
    r = await alice.post(
        url, json=_job(operation="image_edit", inputs=[{"asset_id": up["id"], "role": "image"}])
    )
    assert r.status_code == 422

    mine = (
        await alice.post(
            f"/v1/workspaces/{ws}/uploads", files={"file": ("p.png", _PIXEL, "image/png")}
        )
    ).json()
    # Wrong role for this operation.
    r = await alice.post(
        url, json=_job(operation="image_edit", inputs=[{"asset_id": mine["id"], "role": "mask"}])
    )
    assert r.status_code == 422
    r = await alice.post(
        url, json=_job(operation="image_edit", inputs=[{"asset_id": mine["id"], "role": "image"}])
    )
    assert r.status_code == 201
    assert r.json()["inputs"] == [{"asset_id": mine["id"], "role": "image"}]


async def test_real_models_validate_without_calling_providers(alice):
    ws = await _personal(alice)
    url = f"/v1/workspaces/{ws}/jobs"
    r = await alice.post(
        url,
        json=_job(
            model="vertex/veo-3.1-fast-generate-001",
            operation="text_to_video",
            params={"resolution": "1080p", "duration_seconds": 4},
        ),
    )
    assert r.status_code == 422 and "1080p" in r.json()["detail"]
    r = await alice.post(
        url,
        json=_job(
            model="vertex/veo-3.1-fast-generate-001",
            operation="text_to_video",
            params={"generate_audio": False, "duration_seconds": 4},
        ),
    )
    assert r.status_code == 201
    assert r.json()["estimated_cost_usd"] == 0.4  # $0.10/s x 4s


async def test_cancel(alice):
    ws = await _personal(alice)
    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    job_id = r.json()["id"]
    r = await alice.post(f"/v1/workspaces/{ws}/jobs/{job_id}/cancel")
    assert r.json()["status"] == "canceled"
    await _drain()  # canceled jobs are never picked up
    assert (await alice.get(f"/v1/workspaces/{ws}/jobs/{job_id}")).json()["status"] == "canceled"


async def test_viewer_cannot_generate_or_upload(alice, bob):
    ws = (await alice.post("/v1/workspaces", json={"name": "T"})).json()["id"]
    await alice.post(
        f"/v1/workspaces/{ws}/invitations", json={"email": "bob@example.com", "role": "viewer"}
    )
    [inv] = (await bob.get("/v1/me/invitations")).json()
    await bob.post(f"/v1/me/invitations/{inv['id']}/accept")
    assert (await bob.post(f"/v1/workspaces/{ws}/jobs", json=_job())).status_code == 403
    r = await bob.post(
        f"/v1/workspaces/{ws}/uploads", files={"file": ("p.png", _PIXEL, "image/png")}
    )
    assert r.status_code == 403
