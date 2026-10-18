"""Pydantic models for the YAML content in content/ (see docs/content-schema.md)."""

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DesignStage = Literal["empathise", "define", "ideate", "prototype", "test", "none"]
TemplateKind = Literal["anatomy", "compare", "flow", "checklist", "callout", "spectrum"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


class TechniqueSpec(_Base):
    id: str
    name: str
    category: str
    definition: str
    source: str | None = None


class Criterion(_Base):
    id: str
    name: str
    weight: float = 1
    description: str
    diagnoses_prompt: str | None = None
    anchors: dict[int, str]

    @field_validator("anchors")
    @classmethod
    def _five_anchors(cls, v: dict[int, str]) -> dict[int, str]:
        if sorted(v) != [0, 1, 2, 3, 4]:
            raise ValueError("anchors must define scores 0-4")
        return v


class RubricSpec(_Base):
    id: str
    version: int
    title: str
    criteria: list[Criterion]


class CardSpec(_Base):
    id: str
    title: str
    technique: str | None = None
    template: TemplateKind
    takeaway: str
    body: str | None = None
    data: dict[str, Any]
    source: str | None = None


class TestCase(_Base):
    id: str
    input: str
    note: str | None = None


class Prediction(_Base):
    id: str
    question: str
    options: list[str] = Field(min_length=2)
    answer: int
    explanation: str

    @model_validator(mode="after")
    def _answer_in_range(self) -> "Prediction":
        if not 0 <= self.answer < len(self.options):
            raise ValueError(f"prediction {self.id}: answer index out of range")
        return self


class LabRubric(_Base):
    base: str = "core"
    extra_criteria: list[Criterion] = []


class LabSpec(_Base):
    id: str
    title: str
    difficulty: int = Field(ge=1, le=3)
    estimated_minutes: int = 10
    techniques_targeted: list[str]
    uses_product_case: bool = False
    brief: str
    input_label: str = "Input"
    test_cases: list[TestCase] = Field(min_length=1)
    starter_prompt: str | None = None
    reference_prompt: str
    success_criteria: list[str] = []
    rubric: LabRubric = LabRubric()
    predictions: list[Prediction] = []
    hints: list[str] = []

    def content_version(self) -> str:
        payload = {
            "brief": self.brief,
            "test_cases": [t.model_dump() for t in self.test_cases],
            "success_criteria": self.success_criteria,
            "rubric": self.rubric.model_dump(),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


class ModuleSpec(_Base):
    id: str
    order: int
    title: str
    summary: str
    design_stage: DesignStage = "none"
    design_stage_note: str | None = None
    tier: Literal["free", "pro"] = "pro"
    estimated_minutes: int = 30
    techniques: list[str] = []
    objectives: list[str] = []
    cards: list[str] = []
    labs: list[str] = []


class CourseSpec(_Base):
    id: str
    title: str
    stream: str
    summary: str
    product_case: dict[str, Any]
    modules: list[str]


class ContentBundle(BaseModel):
    course: CourseSpec
    techniques: list[TechniqueSpec]
    rubrics: list[RubricSpec]
    modules: list[ModuleSpec]
    cards: dict[str, CardSpec]
    labs: dict[str, LabSpec]
    card_module: dict[str, str]
    lab_module: dict[str, str]
