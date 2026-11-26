"""Shape of the model catalog (see models.yaml)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Operation = Literal[
    "text_to_image",  # prompt only
    "image_edit",  # prompt + one or more reference images
    "inpaint",  # prompt + image + mask (painted area is regenerated)
    "text_to_video",  # prompt only
    "image_to_video",  # prompt + first frame (+ optional last frame)
    "assemble",  # internal: join video clips into one sequence (storyboards)
]

OPERATION_LABELS: dict[str, str] = {
    "text_to_image": "Text to image",
    "image_edit": "Edit with references",
    "inpaint": "Inpaint (mask)",
    "text_to_video": "Text to video",
    "image_to_video": "Image to video",
    "assemble": "Assemble clips",
}


class Option(BaseModel):
    value: Any
    label: str | None = None


class ParamSpec(BaseModel):
    name: str
    label: str
    type: Literal["enum", "int", "float", "bool", "text", "size"]
    default: Any = None
    options: list[Option] = Field(default_factory=list)
    min: float | None = None
    max: float | None = None
    step: float | None = None
    help: str | None = None
    advanced: bool = False
    # Only offered for these operations (all if empty).
    operations: list[str] = Field(default_factory=list)
    # Only offered when other params have one of these values, e.g. {"output_format": ["gif"]}.
    when: dict[str, list[Any]] = Field(default_factory=dict)
    # For type=size: limits for custom WIDTHxHEIGHT values.
    size_rules: dict[str, float] | None = None


class InputSpec(BaseModel):
    role: Literal["image", "mask", "first_frame", "last_frame", "clip"]
    label: str
    media_type: Literal["image", "video"] = "image"
    min: int = 0
    max: int = 1


class OperationSpec(BaseModel):
    operation: Operation
    inputs: list[InputSpec] = Field(default_factory=list)


class Rule(BaseModel):
    """If params match `if_`, then each param in `then` must be one of the listed values."""

    if_: dict[str, list[Any]] = Field(alias="if")
    then: dict[str, list[Any]]
    message: str


class Rate(BaseModel):
    when: dict[str, list[Any]] = Field(default_factory=dict)
    usd: float


class Pricing(BaseModel):
    unit: Literal["image", "second"]
    rates: list[Rate]
    # Param holding how many outputs are produced (multiplies the price).
    quantity_param: str | None = None
    # Param holding clip length in seconds (unit=second).
    seconds_param: str | None = None
    # Scale per-image price by output area relative to 1024x1024 (token-priced models).
    area_param: str | None = None
    # Token rates (USD per 1M) used to compute the actual cost from provider usage.
    token_rates: dict[str, float] | None = None
    source: str
    verified: bool = False


class ModelSpec(BaseModel):
    id: str  # our stable id, e.g. "openai/gpt-image-2.6-sunburst"
    provider: Literal["openai", "vertex", "debug", "studio"]
    model: str  # provider's model id
    adapter: str  # key in app.providers registry
    name: str
    family: str
    media_type: Literal["image", "video"]
    description: str
    status: Literal["ga", "preview", "deprecated"] = "ga"
    shutdown_date: str | None = None
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    operations: list[OperationSpec]
    params: list[ParamSpec]
    rules: list[Rule] = Field(default_factory=list)
    pricing: Pricing

    def operation(self, name: str) -> OperationSpec | None:
        return next((o for o in self.operations if o.operation == name), None)

    def params_for(self, operation: str) -> list[ParamSpec]:
        return [p for p in self.params if not p.operations or operation in p.operations]
