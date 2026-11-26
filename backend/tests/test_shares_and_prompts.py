from app.providers.debug import PIXEL
from app.services import prompts


async def _upload(user):
    ws = (await user.get("/v1/me")).json()["workspaces"][0]["id"]
    asset = (
        await user.post(
            f"/v1/workspaces/{ws}/uploads", files={"file": ("p.png", PIXEL, "image/png")}
        )
    ).json()
    return ws, asset


async def test_share_link_lifecycle(alice, client):
    ws, asset = await _upload(alice)
    r = await alice.post(f"/v1/workspaces/{ws}/assets/{asset['id']}/shares", json={})
    assert r.status_code == 201
    share = r.json()

    public = await client.http.get(f"/v1/share/{share['token']}")  # no auth
    assert public.status_code == 200
    assert public.json()["media_type"] == "image" and public.json()["prompt"] is None

    listed = (await alice.get(f"/v1/workspaces/{ws}/assets/{asset['id']}/shares")).json()
    assert [s["id"] for s in listed] == [share["id"]]

    assert (await alice.delete(f"/v1/workspaces/{ws}/shares/{share['id']}")).status_code == 204
    assert (await client.http.get(f"/v1/share/{share['token']}")).status_code == 404


async def test_cannot_share_other_workspaces_assets(alice, bob):
    _, asset = await _upload(alice)
    bob_ws = (await bob.get("/v1/me")).json()["workspaces"][0]["id"]
    r = await bob.post(f"/v1/workspaces/{bob_ws}/assets/{asset['id']}/shares", json={})
    assert r.status_code == 404


async def test_unknown_share_token(client):
    assert (await client.http.get("/v1/share/nope")).status_code == 404


async def test_enhance_prompt(alice, monkeypatch):
    seen = {}

    async def fake(prompt, spec):
        seen["args"] = (prompt, spec.id if spec else None)
        return "A detailed prompt"

    monkeypatch.setattr(prompts, "enhance_prompt", fake)
    ws = (await alice.get("/v1/me")).json()["workspaces"][0]["id"]
    r = await alice.post(
        f"/v1/workspaces/{ws}/prompts/enhance",
        json={"prompt": "cat", "model": "vertex/veo-3.1-generate-001"},
    )
    assert r.status_code == 200 and r.json()["prompt"] == "A detailed prompt"
    assert seen["args"] == ("cat", "vertex/veo-3.1-generate-001")


async def test_enhance_prompt_failure_is_502(alice, monkeypatch):
    async def broken(prompt, spec):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(prompts, "enhance_prompt", broken)
    ws = (await alice.get("/v1/me")).json()["workspaces"][0]["id"]
    r = await alice.post(f"/v1/workspaces/{ws}/prompts/enhance", json={"prompt": "cat"})
    assert r.status_code == 502
