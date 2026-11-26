import uuid

import pytest

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.copilot import planner
from app.services.copilot.planner import finalize
from app.services.copilot.schema import Draft, PlanStep, StepInput
from app.services.storage import get_storage
from app.worker.runner import claim_next, run_job

VIDEO_GOAL = "An 8 second vertical teaser video for a cozy coffee shop at sunrise"


@pytest.fixture(autouse=True)
def rules_planner(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "copilot_planner", "rules")
    monkeypatch.setattr(s, "copilot_simulate", False)
    return s


async def _ws(user):
    return (await user.get("/v1/me")).json()["workspaces"][0]["id"]


async def _balance(user, ws):
    return (await user.get(f"/v1/workspaces/{ws}/billing")).json()["balance_usd"]


async def _drain():
    while job := await claim_next(SessionLocal):
        await run_job(job, SessionLocal, get_storage(), get_settings())


async def _plan(user, ws, **body):
    r = await user.post(f"/v1/workspaces/{ws}/copilot/plans", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def test_video_goal_becomes_key_frame_then_animation(alice):
    ws = await _ws(alice)
    plan = await _plan(alice, ws, goal=VIDEO_GOAL)
    assert plan["status"] == "draft" and plan["planner"] == "rules"
    s1, s2 = plan["steps"]
    assert s1["operation"] == "text_to_image" and s2["operation"] == "image_to_video"
    assert s2["inputs"] == [
        {"role": "first_frame", "from_step": "s1", "asset_id": None, "output_index": 0}
    ]
    assert s2["params"]["aspect_ratio"] == "9:16" and s2["params"]["duration_seconds"] == 8
    assert plan["estimated_price_usd"] == pytest.approx(
        s1["estimated_price_usd"] + s2["estimated_price_usd"]
    )
    assert await _balance(alice, ws) == 1.0  # planning is free


async def test_budget_and_preference(alice):
    ws = await _ws(alice)
    cheap = await _plan(alice, ws, goal=VIDEO_GOAL, budget_usd=0.6)
    assert cheap["estimated_price_usd"] <= 0.6
    assert any("budget" in n for n in cheap["notes"])
    best = await _plan(alice, ws, goal="a poster of a lighthouse", preference="quality")
    budget = await _plan(alice, ws, goal="a poster of a lighthouse", preference="budget")
    assert best["estimated_price_usd"] > budget["estimated_price_usd"]
    assert best["steps"][0]["params"]["quality"] == "high"


async def test_plan_uses_attached_image(alice):
    ws = await _ws(alice)
    await alice.post(
        f"/v1/workspaces/{ws}/jobs",
        json={"operation": "text_to_image", "model": "debug/pixel", "prompt": "cat"},
    )
    await _drain()
    [asset] = (await alice.get(f"/v1/workspaces/{ws}/assets")).json()["items"]
    plan = await _plan(alice, ws, goal="animate this, slow zoom", attachments=[asset["id"]])
    [step] = plan["steps"]
    assert step["operation"] == "image_to_video"
    assert step["inputs"][0]["asset_id"] == asset["id"]

    r = await alice.post(
        f"/v1/workspaces/{ws}/copilot/plans",
        json={"goal": "edit it", "attachments": [str(uuid.uuid4())]},
    )
    assert r.status_code == 422


async def test_running_a_plan_chains_outputs(alice, rules_planner, monkeypatch):
    monkeypatch.setattr(rules_planner, "copilot_simulate", True)
    ws = await _ws(alice)
    plan = await _plan(alice, ws, goal=VIDEO_GOAL)
    r = await alice.post(f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}/run")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["status"] == "running"
    assert [s["status"] for s in plan["steps"]] == ["queued", "pending"]

    await _drain()  # key frame, then the clip it unlocks
    plan = (await alice.get(f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}")).json()
    assert plan["status"] == "succeeded", plan
    assert [s["status"] for s in plan["steps"]] == ["succeeded", "succeeded"]
    image_job, video_job = plan["jobs"]
    assert video_job["inputs"][0]["asset_id"] == image_job["outputs"][0]["id"]
    assert video_job["outputs"][0]["media_type"] == "video"
    # Simulated on debug models: $0.011 image + 8s x $0.011 clip.
    assert plan["charged_usd"] == pytest.approx(0.011 + 0.088)
    assert await _balance(alice, ws) == pytest.approx(1.0 - 0.099)


async def test_failed_step_skips_the_rest_and_refunds(alice):
    ws = await _ws(alice)
    plan = await _plan(alice, ws, goal=VIDEO_GOAL)
    base = f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}"
    r = await alice.patch(
        f"{base}/steps/s1", json={"model": "debug/pixel", "params": {"fail": True}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["steps"][0]["estimated_price_usd"] == pytest.approx(0.011)
    await alice.patch(f"{base}/steps/s2", json={"model": "debug/clip"})
    await alice.post(f"{base}/run")
    await _drain()
    plan = (await alice.get(base)).json()
    assert plan["status"] == "failed" and "failed" in plan["error"]
    assert [s["status"] for s in plan["steps"]] == ["failed", "skipped"]
    assert await _balance(alice, ws) == 1.0


async def test_editing_steps(alice):
    ws = await _ws(alice)
    plan = await _plan(alice, ws, goal=VIDEO_GOAL)
    base = f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}"
    r = await alice.patch(f"{base}/steps/s1", json={"prompt": "A red door", "title": "Door"})
    assert r.json()["steps"][0]["prompt"] == "A red door"
    # A model that can't animate an image is refused.
    r = await alice.patch(f"{base}/steps/s2", json={"model": "openai/gpt-image-2.6-sunburst"})
    assert r.status_code == 422
    r = await alice.patch(f"{base}/steps/s2", json={"params": {"duration_seconds": 5}})
    assert r.status_code == 422
    # Deleting the key frame turns the animation into text to video.
    r = await alice.delete(f"{base}/steps/s1")
    [step] = r.json()["steps"]
    assert step["id"] == "s1" and step["operation"] == "text_to_video" and step["inputs"] == []


async def test_not_enough_credit_keeps_the_plan_as_draft(alice):
    ws = await _ws(alice)
    plan = await _plan(alice, ws, goal="animate a dragon flying", preference="quality")
    assert plan["estimated_price_usd"] > 1
    r = await alice.post(f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}/run")
    assert r.status_code == 402 and "Buy credits" in r.json()["detail"]
    plan = (await alice.get(f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}")).json()
    assert plan["status"] == "draft" and plan["jobs"] == []


async def test_cancel_and_rerun_rules(alice, rules_planner, monkeypatch):
    monkeypatch.setattr(rules_planner, "copilot_simulate", True)
    ws = await _ws(alice)
    plan = await _plan(alice, ws, goal=VIDEO_GOAL)
    base = f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}"
    await alice.post(f"{base}/run")
    plan = (await alice.post(f"{base}/cancel")).json()
    assert plan["status"] == "canceled"
    assert [s["status"] for s in plan["steps"]] == ["canceled", "canceled"]
    assert await _balance(alice, ws) == 1.0
    assert (await alice.post(f"{base}/run")).status_code == 409
    assert (await alice.patch(f"{base}/steps/s1", json={"prompt": "x"})).status_code == 409


async def test_autorun_and_revise(alice, bob, rules_planner, monkeypatch):
    monkeypatch.setattr(rules_planner, "copilot_simulate", True)
    ws = await _ws(alice)
    plan = await _plan(alice, ws, goal="a minimalist fox logo", preference="budget", autorun=True)
    assert plan["can_autorun"] and plan["status"] == "running"
    # Too expensive to start on its own.
    plan = await _plan(alice, ws, goal=VIDEO_GOAL, autorun=True)
    assert plan["status"] == "draft"

    revised = (
        await alice.post(
            f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}/revise", json={"preference": "budget"}
        )
    ).json()
    assert revised["preference"] == "budget"
    shorter = (
        await alice.post(
            f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}/revise",
            json={"instruction": "make it 4 seconds"},
        )
    ).json()
    assert shorter["steps"][-1]["params"]["duration_seconds"] == 4
    assert revised["estimated_price_usd"] < plan["estimated_price_usd"]

    assert (await bob.get(f"/v1/workspaces/{ws}/copilot/plans/{plan['id']}")).status_code == 404
    assert len((await alice.get(f"/v1/workspaces/{ws}/copilot/plans")).json()) == 2


def test_finalize_repairs_llm_mistakes():
    image = uuid.uuid4()
    draft = Draft(
        title="Launch",
        planner="llm",
        steps=[
            PlanStep(
                id="a",
                title="Hero",
                model="openai/not-a-model",
                operation="text_to_image",
                prompt="hero shot",
                params={"quality": "ultra", "size": "1536x1024"},
            ),
            PlanStep(
                id="b",
                title="Animate",
                model="vertex/veo-3.1-fast-generate-001",
                operation="image_to_video",
                prompt="push in",
                params={"duration_seconds": 6, "bogus": 1},
                inputs=[
                    StepInput(role="first_frame", from_step="a"),
                    StepInput(role="mask", from_step="a"),
                ],
            ),
            PlanStep(
                id="c",
                title="Edit",
                model="vertex/gemini-3-pro-image",
                operation="image_edit",
                prompt="add logo",
                inputs=[StepInput(role="image", asset_id=uuid.uuid4())],
            ),
        ],
    )
    plan = finalize(draft, "balanced", None, {image: "image"})
    a, b, c = plan.steps
    assert [s.id for s in plan.steps] == ["s1", "s2", "s3"]
    assert (
        a.model != "openai/not-a-model"
        and "quality" not in a.params
        or a.params["quality"] != "ultra"
    )
    assert b.params["duration_seconds"] == 6 and "bogus" not in b.params
    assert [i.model_dump(exclude_none=True) for i in b.inputs] == [
        {"role": "first_frame", "from_step": "s1", "output_index": 0}
    ]
    # The unknown attachment is replaced with the last image step's output.
    assert c.inputs[0].from_step == "s1"
    assert any("instead of openai/not-a-model" in n for n in plan.notes)
    assert all(s.estimated_price_usd > 0 for s in plan.steps)


async def test_llm_planner_falls_back_to_rules(alice, rules_planner, monkeypatch):
    monkeypatch.setattr(rules_planner, "copilot_planner", "llm")

    async def broken(*a, **k):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(planner, "llm_plan", broken)
    plan = await _plan(alice, await _ws(alice), goal="a watercolor map of Lisbon")
    assert plan["planner"] == "rules" and len(plan["steps"]) == 1
