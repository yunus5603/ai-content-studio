import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Workspace
from app.providers.stitch import build_filter
from app.services.storage import get_storage
from app.worker.runner import claim_next, run_job

IMAGE = {"image_model": "debug/pixel", "image_params": {"placeholder": True}}
VIDEO = {"video_model": "debug/clip", "video_params": {"duration_seconds": 4}}


async def _ws(user):
    return (await user.get("/v1/me")).json()["workspaces"][0]["id"]


async def _balance(user, ws):
    return (await user.get(f"/v1/workspaces/{ws}/billing")).json()["balance_usd"]


async def _drain():
    while job := await claim_next(SessionLocal):
        await run_job(job, SessionLocal, get_storage(), get_settings())


async def _board(user, ws, shots=2, **extra):
    body = {
        "title": "Lighthouse",
        "style": "watercolor, dusk",
        **IMAGE,
        **VIDEO,
        "shots": [
            {"title": f"Shot {i + 1}", "description": f"frame {i + 1}", "motion": "slow push in"}
            for i in range(shots)
        ],
        **extra,
    }
    r = await user.post(f"/v1/workspaces/{ws}/storyboards", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_prices_every_step(alice):
    ws = await _ws(alice)
    sb = await _board(alice, ws, shots=3)
    assert [s["position"] for s in sb["shots"]] == [0, 1, 2]
    shot = sb["shots"][0]
    assert shot["keyframe_cost"] == {"price_usd": pytest.approx(0.011), "problem": None}
    # 4 s x $0.01 + 10%, priced up front but flagged until a keyframe exists.
    assert shot["clip_cost"]["price_usd"] == pytest.approx(0.044)
    assert shot["clip_cost"]["problem"] == "Make a keyframe first"
    t = sb["totals"]
    assert t["missing_keyframes_usd"] == pytest.approx(0.033)
    assert t["missing_clips_usd"] == pytest.approx(0.132)
    assert t["seconds"] == 12
    listed = (await alice.get(f"/v1/workspaces/{ws}/storyboards")).json()
    assert [b["shot_count"] for b in listed] == [3]


async def test_defaults_pick_widescreen_models(alice):
    ws = await _ws(alice)
    r = await alice.post(f"/v1/workspaces/{ws}/storyboards", json={"title": "Untitled"})
    assert r.status_code == 201, r.text
    sb = r.json()
    assert sb["image_model"] == "vertex/gemini-nano-banana-2.1"
    assert sb["image_params"] == {"aspect_ratio": "16:9"}
    assert sb["video_model"] == "vertex/veo-3.1-fast-generate-001"
    assert sb["video_params"] == {"aspect_ratio": "16:9"}


async def test_full_flow_keyframes_clips_film(alice):
    ws = await _ws(alice)
    sb = await _board(alice, ws)
    url = f"/v1/workspaces/{ws}/storyboards/{sb['id']}"

    # Clips need keyframes first.
    r = await alice.post(f"{url}/generate", json={"stage": "clips"})
    assert r.status_code == 422 and "keyframe" in r.json()["detail"]

    r = await alice.post(f"{url}/generate", json={"stage": "keyframes"})
    assert r.status_code == 200, r.text
    assert all(s["keyframe_job"]["status"] == "queued" for s in r.json()["shots"])
    assert await _balance(alice, ws) == pytest.approx(1.0 - 0.022)
    # Asking again while they run starts nothing new.
    r = await alice.post(f"{url}/generate", json={"stage": "keyframes"})
    assert await _balance(alice, ws) == pytest.approx(1.0 - 0.022)
    await _drain()

    sb = (await alice.get(url)).json()
    assert all(s["keyframe"] and s["keyframe_job"] is None for s in sb["shots"])
    assert sb["totals"]["keyframes_done"] == 2
    kf0 = sb["shots"][0]["keyframe"]["id"]

    # Keyframes are ordinary jobs, with the style folded into the prompt.
    jobs = (await alice.get(f"/v1/workspaces/{ws}/jobs")).json()["items"]
    assert {j["prompt"] for j in jobs} == {
        "frame 1\n\nStyle: watercolor, dusk",
        "frame 2\n\nStyle: watercolor, dusk",
    }

    r = await alice.post(f"{url}/generate", json={"stage": "clips"})
    assert r.status_code == 200, r.text
    await _drain()
    sb = (await alice.get(url)).json()
    assert all(s["clip"] and not s["clip_stale"] for s in sb["shots"])
    clip_job = next(
        j
        for j in (await alice.get(f"/v1/workspaces/{ws}/jobs")).json()["items"]
        if j["operation"] == "image_to_video" and j["inputs"][0]["asset_id"] == kf0
    )
    assert clip_job["prompt"].startswith("slow push in")
    assert sb["totals"]["spent_usd"] == pytest.approx(0.022 + 0.088)

    r = await alice.post(f"{url}/assemble")
    assert r.status_code == 200, r.text
    assert r.json()["film_job"]["price_usd"] == 0
    await _drain()
    sb = (await alice.get(url)).json()
    film = sb["film"]
    assert film["media_type"] == "video" and film["duration_seconds"] == pytest.approx(8, abs=0.2)
    assert not sb["film_stale"]
    assert sb["totals"]["spent_usd"] == pytest.approx(0.11)  # assembly is free

    # Swapping shot order makes the film out of date.
    ids = [s["id"] for s in sb["shots"]]
    sb = (await alice.put(f"{url}/order", json={"shot_ids": ids[::-1]})).json()
    assert sb["film_stale"]

    # Picking a different keyframe flags that shot's clip as out of date.
    other = sb["shots"][1]["keyframe"]["id"]
    sb = (
        await alice.put(f"{url}/shots/{sb['shots'][0]['id']}/keyframe", json={"asset_id": other})
    ).json()
    assert sb["shots"][0]["clip_stale"]
    assert sb["totals"]["missing_clips_usd"] == pytest.approx(0.044)


async def test_crossfade_assembly(alice):
    ws = await _ws(alice)
    sb = await _board(alice, ws, transition="fade")
    url = f"/v1/workspaces/{ws}/storyboards/{sb['id']}"
    await alice.post(f"{url}/generate", json={"stage": "keyframes"})
    await _drain()
    await alice.post(f"{url}/generate", json={"stage": "clips"})
    await _drain()
    await alice.post(f"{url}/assemble")
    await _drain()
    film = (await alice.get(url)).json()["film"]
    assert film["duration_seconds"] == pytest.approx(7.5, abs=0.2)  # 4 + 4 - 0.5 fade


async def test_batch_is_all_or_nothing_on_credits(alice):
    ws = await _ws(alice)
    sb = await _board(alice, ws, shots=3)
    async with SessionLocal() as s:
        await s.execute(update(Workspace).where(Workspace.id == ws).values(balance_micros=20_000))
        await s.commit()
    r = await alice.post(
        f"/v1/workspaces/{ws}/storyboards/{sb['id']}/generate", json={"stage": "keyframes"}
    )
    assert r.status_code == 402
    assert "3 generations" in r.json()["detail"]
    sb = (await alice.get(f"/v1/workspaces/{ws}/storyboards/{sb['id']}")).json()
    assert all(s["keyframe_job"] is None for s in sb["shots"])
    assert await _balance(alice, ws) == pytest.approx(0.02)


async def test_shot_editing_and_references(alice):
    ws = await _ws(alice)
    sb = await _board(alice, ws)
    url = f"/v1/workspaces/{ws}/storyboards/{sb['id']}"
    sb = (await alice.post(f"{url}/shots", json={"description": "opener", "position": 0})).json()
    assert [s["description"] for s in sb["shots"]] == ["opener", "frame 1", "frame 2"]
    first = sb["shots"][0]["id"]
    sb = (await alice.delete(f"{url}/shots/{sb['shots'][1]['id']}")).json()
    assert [s["position"] for s in sb["shots"]] == [0, 1]

    # A reference image switches the keyframe to an edit-with-references job.
    from app.providers.debug import PIXEL

    up = (
        await alice.post(
            f"/v1/workspaces/{ws}/uploads", files={"file": ("hero.png", PIXEL, "image/png")}
        )
    ).json()
    r = await alice.patch(f"{url}/shots/{first}", json={"reference_asset_ids": [up["id"]]})
    assert r.status_code == 200, r.text
    assert [a["id"] for a in r.json()["shots"][0]["references"]] == [up["id"]]
    await alice.post(f"{url}/generate", json={"stage": "keyframes", "shot_ids": [first]})
    [job] = (await alice.get(f"/v1/workspaces/{ws}/jobs")).json()["items"]
    assert job["operation"] == "image_edit" and job["inputs"][0]["asset_id"] == up["id"]

    # Invalid model settings are rejected when saved.
    r = await alice.patch(url, json={"image_params": {"placeholder": "yes"}})
    assert r.status_code == 422


async def test_permissions(alice, bob):
    ws = await _ws(alice)
    sb = await _board(alice, ws)
    url = f"/v1/workspaces/{ws}/storyboards/{sb['id']}"
    assert (await bob.get(url)).status_code in (403, 404)

    team = (await alice.post("/v1/workspaces", json={"name": "Team"})).json()["id"]
    await alice.post(
        f"/v1/workspaces/{team}/invitations", json={"email": "bob@example.com", "role": "viewer"}
    )
    [inv] = (await bob.get("/v1/me/invitations")).json()
    await bob.post(f"/v1/me/invitations/{inv['id']}/accept")
    tsb = await _board(alice, team)
    turl = f"/v1/workspaces/{team}/storyboards/{tsb['id']}"
    assert (await bob.get(turl)).status_code == 200
    assert (await bob.post(f"{turl}/generate", json={"stage": "keyframes"})).status_code == 403
    assert (await bob.patch(turl, json={"title": "x"})).status_code == 403


def test_build_filter_offsets():
    graph, total = build_filter([(4.0, True), (6.0, False), (4.0, True)], 1280, 720, "fade", 0.5)
    assert "xfade=transition=fade:duration=0.500:offset=3.500" in graph
    assert "offset=9.000" in graph  # 4 + 6 - 2 x 0.5
    assert "anullsrc" in graph  # clip without audio gets silence
    assert total == pytest.approx(13.0)
    graph, total = build_filter([(4.0, True), (4.0, True)], 1280, 720, "cut", 0.5)
    assert "concat=n=2:v=1:a=1" in graph and total == 8.0
