"""Adapters against fake SDK clients: checks what we send and how we handle replies."""

import base64
import uuid
from types import SimpleNamespace as NS

import pytest

from app.catalog import load_catalog, validate_params
from app.models import Asset, AssetKind, Job, MediaType
from app.providers import ProviderError, openai_image, vertex_gemini_image, vertex_veo
from app.providers.debug import PIXEL


class FakeCtx:
    def __init__(self, model_id, operation, params, inputs=None, external_id=None):
        self.spec = load_catalog()[model_id]
        self.params = validate_params(self.spec, operation, params)
        self.job = Job(
            id=uuid.uuid4(),
            operation=operation,
            prompt="a red fox",
            created_by_id=uuid.uuid4(),
            external_id=external_id,
        )
        self._inputs = inputs or {}
        self.usage = None
        self.progress = []
        self.external_ids = []

    def inputs(self, role):
        return self._inputs.get(role, [])

    async def report_progress(self, p):
        self.progress.append(p)

    async def set_external_id(self, value):
        self.external_ids.append(value)

    async def is_canceled(self):
        return False


def _asset(name="a.png"):
    return Asset(
        filename=name, content_type="image/png", media_type=MediaType.image, kind=AssetKind.upload
    )


class FakeImages:
    def __init__(self):
        self.calls = []

    def _resp(self, n):
        return NS(
            data=[NS(b64_json=base64.b64encode(PIXEL).decode())] * n,
            usage=NS(output_tokens=1000, input_tokens_details=NS(text_tokens=50, image_tokens=0)),
        )

    async def generate(self, **kw):
        self.calls.append(("generate", kw))
        return self._resp(kw.get("n", 1))

    async def edit(self, **kw):
        self.calls.append(("edit", kw))
        return self._resp(kw.get("n", 1))


@pytest.fixture
def fake_openai(monkeypatch):
    images = FakeImages()
    monkeypatch.setattr(openai_image, "openai_client", lambda: NS(images=images))
    return images


async def test_openai_generate(fake_openai):
    ctx = FakeCtx(
        "openai/gpt-image-2.6-sunburst",
        "text_to_image",
        {"n": 2, "size": "1536x1024", "output_format": "webp"},
    )
    out = await openai_image.run(ctx)
    [(kind, kw)] = fake_openai.calls
    assert kind == "generate"
    assert kw["model"] == "gpt-image-2.6-sunburst" and kw["n"] == 2 and kw["size"] == "1536x1024"
    assert "input_fidelity" not in kw
    assert len(out) == 2 and out[0].content_type == "image/webp" and out[0].width == 1536
    assert ctx.usage == {"text_input_tokens": 50, "image_input_tokens": 0, "output_tokens": 1000}


async def test_openai_inpaint_sends_image_and_mask(fake_openai):
    ctx = FakeCtx(
        "openai/gpt-image-2.6-flare",
        "inpaint",
        {},
        inputs={"image": [(_asset(), PIXEL)], "mask": [(_asset("m.png"), b"MASK")]},
    )
    await openai_image.run(ctx)
    [(kind, kw)] = fake_openai.calls
    assert kind == "edit"
    assert kw["image"][0][1] == PIXEL and kw["mask"][1] == b"MASK"
    assert kw["input_fidelity"] == "high"


class FakeModels:
    def __init__(self, parts):
        self.parts = parts
        self.calls = []

    async def generate_content(self, **kw):
        self.calls.append(kw)
        return NS(candidates=[NS(content=NS(parts=self.parts), finish_reason="STOP")])


async def test_gemini_image(monkeypatch):
    models = FakeModels([NS(inline_data=NS(data=PIXEL, mime_type="image/png"), text=None)])
    monkeypatch.setattr(vertex_gemini_image, "vertex_client", lambda: NS(aio=NS(models=models)))
    ctx = FakeCtx(
        "vertex/gemini-nano-banana-2.1",
        "image_edit",
        {"n": 3, "aspect_ratio": "16:9", "image_size": "2K"},
        inputs={"image": [(_asset(), PIXEL)]},
    )
    out = await vertex_gemini_image.run(ctx)
    assert len(out) == 3 and len(models.calls) == 3
    call = models.calls[0]
    assert call["model"] == "gemini-nano-banana-2.1"
    assert call["config"].image_config.aspect_ratio == "16:9"
    assert call["config"].image_config.image_size == "2K"
    assert len(call["contents"]) == 2  # reference image + prompt


async def test_gemini_no_image_is_a_clear_error(monkeypatch):
    models = FakeModels([NS(inline_data=None, text="I can't make that.")])
    monkeypatch.setattr(vertex_gemini_image, "vertex_client", lambda: NS(aio=NS(models=models)))
    ctx = FakeCtx("vertex/gemini-3.1-flash-image", "text_to_image", {})
    with pytest.raises(ProviderError, match="can't make that"):
        await vertex_gemini_image.run(ctx)


class FakeVeo:
    def __init__(self, done_after=1, videos=True):
        self.polls = 0
        self.done_after = done_after
        self.videos = videos
        self.created = []

    def _op(self, done):
        response = None
        if done:
            vids = [NS(video=NS(video_bytes=b"MP4", uri=None, mime_type="video/mp4"))]
            response = NS(
                generated_videos=vids if self.videos else [],
                rai_media_filtered_reasons=["unsafe content"],
            )
        return NS(name="operations/123", done=done, error=None, response=response, result=None)

    async def generate_videos(self, **kw):
        self.created.append(kw)
        return self._op(False)

    async def get(self, op):
        self.polls += 1
        return self._op(self.polls >= self.done_after)


@pytest.fixture
def fake_veo(monkeypatch):
    veo = FakeVeo()
    monkeypatch.setattr(
        vertex_veo, "vertex_client", lambda location=None: NS(aio=NS(models=veo, operations=veo))
    )
    monkeypatch.setattr(vertex_veo, "POLL_SECONDS", 0)
    return veo


async def test_veo_image_to_video(fake_veo):
    ctx = FakeCtx(
        "vertex/veo-3.1-generate-001",
        "image_to_video",
        {"aspect_ratio": "9:16", "resolution": "1080p"},
        inputs={"first_frame": [(_asset(), PIXEL)], "last_frame": [(_asset(), b"L")]},
    )
    out = await vertex_veo.run(ctx)
    [call] = fake_veo.created
    assert call["model"] == "veo-3.1-generate-001"
    assert call["source"].image.image_bytes == PIXEL
    assert call["config"].last_frame.image_bytes == b"L"
    assert call["config"].duration_seconds == 8 and call["config"].generate_audio is True
    assert ctx.external_ids == ["operations/123"]
    assert out[0].data == b"MP4" and (out[0].width, out[0].height) == (1080, 1920)


async def test_veo_resumes_existing_operation(fake_veo):
    ctx = FakeCtx(
        "vertex/veo-3.1-fast-generate-001", "text_to_video", {}, external_id="operations/123"
    )
    out = await vertex_veo.run(ctx)
    assert fake_veo.created == []  # no second (paid) generation
    assert len(out) == 1


async def test_veo_blocked(fake_veo):
    fake_veo.videos = False
    ctx = FakeCtx("vertex/veo-3.1-fast-generate-001", "text_to_video", {})
    with pytest.raises(ProviderError, match="unsafe content"):
        await vertex_veo.run(ctx)
