import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import User
from app.services.storage import get_storage
from app.worker.runner import claim_next, run_job


def _job(**overrides):
    body = {"operation": "text_to_image", "model": "debug/pixel", "prompt": "a cat"}
    body.update(overrides)
    return body


async def _ws(user):
    return (await user.get("/v1/me")).json()["workspaces"][0]["id"]


async def _balance(user, ws):
    return (await user.get(f"/v1/workspaces/{ws}/billing")).json()["balance_usd"]


async def _drain():
    while job := await claim_next(SessionLocal):
        await run_job(job, SessionLocal, get_storage(), get_settings())


async def test_signup_credit_and_charging(alice):
    ws = await _ws(alice)
    assert await _balance(alice, ws) == 1.0

    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job(params={"n": 2}))
    job = r.json()
    assert job["estimated_price_usd"] == pytest.approx(0.022)
    assert await _balance(alice, ws) == pytest.approx(1.0 - 0.022)  # held

    await _drain()
    job = (await alice.get(f"/v1/workspaces/{ws}/jobs/{job['id']}")).json()
    assert job["price_usd"] == pytest.approx(0.022)
    assert await _balance(alice, ws) == pytest.approx(0.978)

    s = (await alice.get(f"/v1/workspaces/{ws}/billing")).json()
    assert s["spent_this_month_usd"] == pytest.approx(0.022)
    assert s["my_spent_this_month_usd"] == pytest.approx(0.022)


async def test_failed_and_canceled_jobs_are_refunded(alice):
    ws = await _ws(alice)
    await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job(params={"fail": True}))
    await _drain()
    assert await _balance(alice, ws) == 1.0

    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    await alice.post(f"/v1/workspaces/{ws}/jobs/{r.json()['id']}/cancel")
    assert await _balance(alice, ws) == 1.0


async def test_canceling_a_running_job_charges_the_estimate(alice):
    ws = await _ws(alice)
    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    job = await claim_next(SessionLocal)  # worker picked it up
    cancel = await alice.post(f"/v1/workspaces/{ws}/jobs/{r.json()['id']}/cancel")
    assert cancel.json()["price_usd"] == pytest.approx(0.011)
    await run_job(job, SessionLocal, get_storage(), get_settings())  # finishes; no double charge
    assert await _balance(alice, ws) == pytest.approx(1.0 - 0.011)


async def test_insufficient_credits(alice):
    ws = (await alice.post("/v1/workspaces", json={"name": "Team"})).json()["id"]
    assert await _balance(alice, ws) == 0  # team workspaces get no free credit
    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    assert r.status_code == 402 and "Buy credits" in r.json()["detail"]
    assert (await alice.get(f"/v1/workspaces/{ws}/jobs")).json()["items"] == []


async def test_holds_prevent_overspending(alice):
    ws = await _ws(alice)
    # Veo 3.1 with audio, 8s: $3.20 + 10% = $3.52 > $1 balance.
    r = await alice.post(
        f"/v1/workspaces/{ws}/jobs",
        json=_job(model="vertex/veo-3.1-generate-001", operation="text_to_video"),
    )
    assert r.status_code == 402
    # Fast, no audio, 4s: $0.40 + 10% = $0.44. Two fit, the third doesn't.
    fast = _job(
        model="vertex/veo-3.1-fast-generate-001",
        operation="text_to_video",
        params={"generate_audio": False, "duration_seconds": 4},
    )
    assert (await alice.post(f"/v1/workspaces/{ws}/jobs", json=fast)).status_code == 201
    assert (await alice.post(f"/v1/workspaces/{ws}/jobs", json=fast)).status_code == 201
    assert (await alice.post(f"/v1/workspaces/{ws}/jobs", json=fast)).status_code == 402
    assert await _balance(alice, ws) == pytest.approx(0.12)


async def test_workspace_and_member_limits(alice, bob):
    ws = (await alice.post("/v1/workspaces", json={"name": "Team"})).json()["id"]
    await alice.post(f"/v1/workspaces/{ws}/billing/dev-topup", json={"amount_usd": 10})
    await alice.post(
        f"/v1/workspaces/{ws}/invitations", json={"email": "bob@example.com", "role": "member"}
    )
    [inv] = (await bob.get("/v1/me/invitations")).json()
    await bob.post(f"/v1/me/invitations/{inv['id']}/accept")
    bob_id = (await bob.get("/v1/me")).json()["user"]["id"]

    # Only the owner sets the workspace limit; admins set member limits.
    assert (
        await bob.put(f"/v1/workspaces/{ws}/billing/limit", json={"monthly_limit_usd": 1})
    ).status_code == 403
    r = await alice.put(
        f"/v1/workspaces/{ws}/members/{bob_id}/limit", json={"monthly_limit_usd": 0.02}
    )
    assert r.json()["monthly_limit_micros"] == 20_000

    assert (await bob.post(f"/v1/workspaces/{ws}/jobs", json=_job())).status_code == 201
    r = await bob.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    assert r.status_code == 403 and "your monthly" in r.json()["detail"]
    # Alice has no personal limit.
    assert (await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())).status_code == 201

    await alice.put(f"/v1/workspaces/{ws}/billing/limit", json={"monthly_limit_usd": 0.03})
    r = await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    assert r.status_code == 403 and "workspace" in r.json()["detail"]
    await alice.put(f"/v1/workspaces/{ws}/billing/limit", json={"monthly_limit_usd": None})
    assert (await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())).status_code == 201


async def test_ledger_and_usage_visibility(alice, bob):
    ws = (await alice.post("/v1/workspaces", json={"name": "Team"})).json()["id"]
    await alice.post(f"/v1/workspaces/{ws}/billing/dev-topup", json={"amount_usd": 5})
    await alice.post(
        f"/v1/workspaces/{ws}/invitations", json={"email": "bob@example.com", "role": "member"}
    )
    [inv] = (await bob.get("/v1/me/invitations")).json()
    await bob.post(f"/v1/me/invitations/{inv['id']}/accept")
    await alice.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    await bob.post(f"/v1/workspaces/{ws}/jobs", json=_job(params={"n": 3}))
    await _drain()

    owner_view = (await alice.get(f"/v1/workspaces/{ws}/billing/entries")).json()["items"]
    assert [e["kind"] for e in owner_view].count("job_hold") == 2
    member_view = (await bob.get(f"/v1/workspaces/{ws}/billing/entries")).json()["items"]
    assert [e["kind"] for e in member_view] == ["job_hold"]

    report = (await alice.get(f"/v1/workspaces/{ws}/billing/usage")).json()
    assert report["jobs"] == 2 and report["total_usd"] == pytest.approx(0.044)
    assert {r["label"] for r in report["by_member"]} == {"alice@example.com", "bob@example.com"}
    assert report["by_model"][0]["label"] == "Debug pixel"
    mine = (await bob.get(f"/v1/workspaces/{ws}/billing/usage")).json()
    assert mine["jobs"] == 1 and mine["total_usd"] == pytest.approx(0.033)


async def test_checkout_requires_stripe_and_owner(alice):
    ws = await _ws(alice)
    r = await alice.post(f"/v1/workspaces/{ws}/billing/checkout", json={"amount_usd": 10})
    assert r.status_code == 503


def _signed(payload: dict, secret: str) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={ts},v1={sig}"


async def test_stripe_webhook_credits_once(alice, client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    ws = await _ws(alice)
    event = {
        "id": "evt_1",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "object": "checkout.session",
                "payment_status": "paid",
                "metadata": {"workspace_id": ws, "credit_micros": "10000000"},
            }
        },
    }
    body, header = _signed(event, "whsec_test")
    for _ in range(2):  # Stripe may deliver twice
        r = await client.http.post(
            "/v1/billing/stripe/webhook", content=body, headers={"Stripe-Signature": header}
        )
        assert r.status_code == 200
    assert await _balance(alice, ws) == 11.0

    bad = await client.http.post(
        "/v1/billing/stripe/webhook", content=body, headers={"Stripe-Signature": "t=1,v1=bad"}
    )
    assert bad.status_code == 400


async def test_admin_dashboard(alice, bob):
    await alice.get("/v1/me")
    ws = await _ws(bob)
    await bob.post(f"/v1/workspaces/{ws}/jobs", json=_job())
    await _drain()
    assert (await alice.get("/v1/admin/overview")).status_code == 404  # not staff

    async with SessionLocal() as s:
        await s.execute(
            update(User).where(User.email == "alice@example.com").values(is_platform_admin=True)
        )
        await s.commit()
    o = (await alice.get("/v1/admin/overview")).json()
    assert o["users"] == 2 and o["jobs"] == 1
    assert o["customer_spend_usd"] == pytest.approx(0.011)
    assert o["provider_cost_usd"] == pytest.approx(0.01)
    assert o["margin_usd"] == pytest.approx(0.001)
    assert o["free_credit_granted_usd"] == 2.0

    rows = (await alice.get("/v1/admin/workspaces", params={"q": "bob"})).json()
    assert len(rows) == 1 and rows[0]["owner_email"] == "bob@example.com"
    r = await alice.post(
        f"/v1/admin/workspaces/{ws}/credits", json={"amount_usd": 5, "reason": "Support goodwill"}
    )
    assert r.json()["balance_usd"] == pytest.approx(1.0 - 0.011 + 5)
