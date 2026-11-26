async def _team(user, name="Team"):
    r = await user.post("/v1/workspaces", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


async def test_first_request_creates_user_and_personal_workspace(alice):
    r = await alice.get("/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "alice@example.com"
    [ws] = body["workspaces"]
    assert ws["is_personal"] and ws["role"] == "owner"
    assert "manage_billing" in ws["permissions"]
    # Idempotent: second call doesn't create another workspace.
    assert len((await alice.get("/v1/me")).json()["workspaces"]) == 1


async def test_requires_auth(client):
    r = await client.http.get("/v1/me")
    assert r.status_code == 401


async def test_outsiders_get_404(alice, bob):
    ws = await _team(alice)
    await bob.get("/v1/me")
    assert (await bob.get(f"/v1/workspaces/{ws}")).status_code == 404


async def test_invite_accept_and_role_rules(alice, bob, client):
    ws = await _team(alice)
    r = await alice.post(
        f"/v1/workspaces/{ws}/invitations", json={"email": "Bob@Example.com", "role": "viewer"}
    )
    assert r.status_code == 201
    assert (
        await alice.post(f"/v1/workspaces/{ws}/invitations", json={"email": "bob@example.com"})
    ).status_code == 409

    me = (await bob.get("/v1/me")).json()
    assert me["pending_invitations"] == 1
    [inv] = (await bob.get("/v1/me/invitations")).json()
    assert inv["workspace_name"] == "Team"
    assert (await bob.post(f"/v1/me/invitations/{inv['id']}/accept")).status_code == 204

    bob_id = me["user"]["id"]
    # Viewer can look but not invite or generate.
    assert (await bob.get(f"/v1/workspaces/{ws}/members")).status_code == 200
    assert (
        await bob.post(f"/v1/workspaces/{ws}/invitations", json={"email": "c@example.com"})
    ).status_code == 403

    # Owner promotes bob to admin; admin can invite but can't touch the owner.
    r = await alice.patch(f"/v1/workspaces/{ws}/members/{bob_id}", json={"role": "admin"})
    assert r.json()["role"] == "admin"
    assert (
        await bob.post(f"/v1/workspaces/{ws}/invitations", json={"email": "c@example.com"})
    ).status_code == 201
    alice_id = (await alice.get("/v1/me")).json()["user"]["id"]
    assert (
        await bob.patch(f"/v1/workspaces/{ws}/members/{alice_id}", json={"role": "member"})
    ).status_code == 403
    assert (
        await bob.patch(f"/v1/workspaces/{ws}/members/{bob_id}", json={"role": "owner"})
    ).status_code == 403
    # Admin can't rename or delete the workspace.
    assert (await bob.patch(f"/v1/workspaces/{ws}", json={"name": "x"})).status_code == 403

    # Anyone can leave.
    assert (await bob.delete(f"/v1/workspaces/{ws}/members/{bob_id}")).status_code == 204
    assert (await bob.get(f"/v1/workspaces/{ws}")).status_code == 404


async def test_personal_workspace_rules(alice):
    ws = (await alice.get("/v1/me")).json()["workspaces"][0]["id"]
    assert (await alice.delete(f"/v1/workspaces/{ws}")).status_code == 400
    assert (
        await alice.post(f"/v1/workspaces/{ws}/invitations", json={"email": "x@example.com"})
    ).status_code == 400
