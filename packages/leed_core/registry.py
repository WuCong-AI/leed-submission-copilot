from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_ROOT = ROOT / "data" / "rating_systems"
REQUIRED_MODULE_FILES = {
    "credit.yaml", "evidence_schema.json", "phase_tasks.yaml", "review_rules.yaml",
    "tender_requirements.yaml", "submittal_template.md", "comment_risk_rules.yaml",
}


@dataclass(frozen=True)
class CreditModule:
    leed_version: str
    rating_family: str
    adaptation: str
    credit_id: str
    credit_code: str
    credit_name: str
    category: str
    is_prerequisite: bool
    max_points: int | None
    module_type: str
    registry_path: str
    official_source_status: str
    raw: dict[str, Any]


class RegistryService:
    def module_root(self, version: str, family: str, adaptation: str) -> Path:
        return REGISTRY_ROOT / version / family / adaptation

    def list_credits(self, version: str, family: str, adaptation: str) -> list[CreditModule]:
        base = self.module_root(version, family, adaptation)
        if not base.exists():
            return []
        modules = [self._load(path) for path in sorted(base.glob("*/credit.yaml"))]
        return modules

    def get_credit(self, version: str, family: str, adaptation: str, credit_id: str) -> CreditModule:
        path = self.module_root(version, family, adaptation) / credit_id / "credit.yaml"
        if not path.exists():
            raise KeyError(f"Registry credit module not found: {version}/{family}/{adaptation}/{credit_id}")
        return self._load(path)

    def load_registry(self, version: str, family: str, adaptation: str) -> dict[str, Any]:
        modules = self.list_credits(version, family, adaptation)
        base = self.module_root(version, family, adaptation)
        return {
            "leed_version": version,
            "rating_family": family,
            "adaptation": adaptation,
            "registry_path": str(base.relative_to(ROOT)).replace("\\", "/"),
            "registry_hash": sha256("".join(m.registry_path for m in modules).encode()).hexdigest(),
            "credits": modules,
        }

    def validate_registry(self, version: str, family: str, adaptation: str) -> dict[str, Any]:
        issues: list[str] = []
        modules = self.list_credits(version, family, adaptation)
        if not modules:
            issues.append("No credit modules found.")
        for module in modules:
            folder = ROOT / module.registry_path
            missing = REQUIRED_MODULE_FILES.difference(item.name for item in folder.iterdir())
            if missing:
                issues.append(f"{module.credit_id}: missing {', '.join(sorted(missing))}")
            if module.raw.get("official_source_status") != "provided_by_user":
                issues.append(f"{module.credit_id}: official requirements are {module.raw.get('official_source_status', 'NEED_OFFICIAL_SOURCE')}.")
        return {"valid": not any("missing" in issue or "No credit" in issue for issue in issues), "issues": issues, "credit_count": len(modules)}

    def _load(self, path: Path) -> CreditModule:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        required = {"leed_version", "rating_family", "adaptation", "credit_id", "credit_code", "credit_name", "category", "is_prerequisite", "module_type"}
        absent = required.difference(raw)
        if absent:
            raise ValueError(f"{path}: missing required fields {sorted(absent)}")
        return CreditModule(
            leed_version=raw["leed_version"], rating_family=raw["rating_family"], adaptation=raw["adaptation"],
            credit_id=raw["credit_id"], credit_code=raw["credit_code"], credit_name=raw["credit_name"],
            category=raw["category"], is_prerequisite=bool(raw["is_prerequisite"]),
            max_points=raw.get("max_points"), module_type=raw["module_type"],
            registry_path=str(path.parent.relative_to(ROOT)).replace("\\", "/"),
            official_source_status=raw.get("official_source_status", "NEED_OFFICIAL_SOURCE"), raw=raw,
        )
