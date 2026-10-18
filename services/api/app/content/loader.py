"""Load and cross-validate the YAML content tree."""

from pathlib import Path

import yaml

from app.content.schema import (
    CardSpec,
    ContentBundle,
    CourseSpec,
    LabSpec,
    ModuleSpec,
    RubricSpec,
    TechniqueSpec,
)


class ContentError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ContentError([f"{path}: expected a mapping"])
    return data


def load_content(root: Path) -> ContentBundle:
    problems: list[str] = []
    course = CourseSpec(**_read(root / "course.yaml"))
    techniques = [TechniqueSpec(**t) for t in _read(root / "techniques.yaml")["techniques"]]
    rubrics = [RubricSpec(**_read(p)) for p in sorted((root / "rubrics").glob("*.yaml"))]
    technique_ids = {t.id for t in techniques}
    rubric_ids = {r.id for r in rubrics}

    modules: list[ModuleSpec] = []
    cards: dict[str, CardSpec] = {}
    labs: dict[str, LabSpec] = {}
    card_module: dict[str, str] = {}
    lab_module: dict[str, str] = {}

    for module_id in course.modules:
        mdir = root / "modules" / module_id
        if not (mdir / "module.yaml").exists():
            problems.append(f"course lists {module_id} but {mdir}/module.yaml is missing")
            continue
        try:
            module = ModuleSpec(**_read(mdir / "module.yaml"))
        except Exception as exc:  # pydantic ValidationError, yaml errors
            problems.append(f"{mdir}/module.yaml: {exc}")
            continue
        if module.id != module_id:
            problems.append(f"{mdir}/module.yaml: id {module.id!r} does not match folder")
        modules.append(module)

        for path in sorted((mdir / "cards").glob("*.yaml")):
            try:
                card = CardSpec(**_read(path))
            except Exception as exc:
                problems.append(f"{path}: {exc}")
                continue
            cards[card.id] = card
            card_module[card.id] = module.id
            if card.technique and card.technique not in technique_ids:
                problems.append(f"{path}: unknown technique {card.technique!r}")
        for path in sorted((mdir / "labs").glob("*.yaml")):
            try:
                lab = LabSpec(**_read(path))
            except Exception as exc:
                problems.append(f"{path}: {exc}")
                continue
            labs[lab.id] = lab
            lab_module[lab.id] = module.id
            for t in lab.techniques_targeted:
                if t not in technique_ids:
                    problems.append(f"{path}: unknown technique {t!r}")
            if lab.rubric.base not in rubric_ids:
                problems.append(f"{path}: unknown rubric {lab.rubric.base!r}")
            if "{{input}}" not in lab.reference_prompt:
                problems.append(f"{path}: reference_prompt must contain {{{{input}}}}")
            case_ids = [t.id for t in lab.test_cases]
            if len(set(case_ids)) != len(case_ids):
                problems.append(f"{path}: duplicate test case ids")

        for t in module.techniques:
            if t not in technique_ids:
                problems.append(f"{mdir}/module.yaml: unknown technique {t!r}")
        for cid in module.cards:
            if card_module.get(cid) != module.id:
                problems.append(f"{mdir}/module.yaml: card {cid!r} not found in module")
        for lid in module.labs:
            if lab_module.get(lid) != module.id:
                problems.append(f"{mdir}/module.yaml: lab {lid!r} not found in module")

    if problems:
        raise ContentError(problems)
    return ContentBundle(
        course=course,
        techniques=techniques,
        rubrics=rubrics,
        modules=sorted(modules, key=lambda m: m.order),
        cards=cards,
        labs=labs,
        card_module=card_module,
        lab_module=lab_module,
    )
