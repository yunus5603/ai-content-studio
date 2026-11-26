import httpx

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.storage import get_storage
from app.worker.registry import _PIXEL
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


async def test_job_lifecycle(alice):
    ws = await _personal(alice)
    r = await alice.post(
        f"/v1/workspaces/{ws}/jobs",
        json={
            "operation": "text_to_image",
            "provider": "debug",
            "model": "pixel",
            "prompt": "a cat",
            "params": {"n": 2},
        },
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    assert r.json()["status"] == "queued"

    await _drain()
    job = (await alice.get(f"/v1/workspaces/{ws}/jobs/{job_id}")).json()
    assert job["status"] == "succeeded" and job["progress"] == 1.0
    assert len(job["outputs"]) == 2
    outputs = (await alice.get(f"/v1/workspaces/{ws}/assets?kind=output")).json()["items"]
    assert len(outputs) == 2  # saved to the gallery automatically


async def test_failed_job_records_error(alice):
    ws = await _personal(alice)
    r = await alice.post(
        f"/v1/workspaces/{ws}/jobs",
        json={
            "operation": "text_to_image",
            "provider": "debug",
            "model": "pixel",
            "params": {"fail": True},
        },
    )
    await _drain()
    job = (await alice.get(f"/v1/workspaces/{ws}/jobs/{r.json()['id']}")).json()
    assert job["status"] == "failed" and "Debug failure" in job["error"]


async def test_unknown_model_and_foreign_inputs_rejected(alice, bob):
    ws = await _personal(alice)
    r = await alice.post(
        f"/v1/workspaces/{ws}/jobs",
        json={"operation": "text_to_image", "provider": "openai", "model": "nope"},
    )
    assert r.status_code == 422

    bob_ws = await _personal(bob)
    up = (
        await bob.post(
            f"/v1/workspaces/{bob_ws}/uploads", files={"file": ("p.png", _PIXEL, "image/png")}
        )
    ).json()
    r = await alice.post(
        f"/v1/workspaces/{ws}/jobs",
        json={
            "operation": "text_to_image",
            "provider": "debug",
            "model": "pixel",
            "input_asset_ids": [up["id"]],
        },
    )
    assert r.status_code == 422


async def test_cancel(alice):
    ws = await _personal(alice)
    r = await alice.post(
        f"/v1/workspaces/{ws}/jobs",
        json={"operation": "text_to_image", "provider": "debug", "model": "pixel"},
    )
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
    r = await bob.post(
        f"/v1/workspaces/{ws}/jobs",
        json={"operation": "text_to_image", "provider": "debug", "model": "pixel"},
    )
    assert r.status_code == 403
    r = await bob.post(
        f"/v1/workspaces/{ws}/uploads", files={"file": ("p.png", _PIXEL, "image/png")}
    )
    assert r.status_code == 403
