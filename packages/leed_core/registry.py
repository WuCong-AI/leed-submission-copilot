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
    BUILTIN_CATALOG = [
        ("IPp1", "IP Prerequisite", "Integrative Process", True, None, "integrative_process"),
        ("LTp1", "Transportation Performance", "Location & Transportation", True, None, "location_transportation"),
        ("SSc1", "Site Assessment", "Sustainable Sites", False, 2, "site"),
        ("SSc2", "Biodiversity and Ecosystem Conservation", "Sustainable Sites", False, 2, "biodiversity"),
        ("WEp1", "Water Performance", "Water Efficiency", True, None, "water"),
        ("WEc1", "Indoor and Outdoor Water Use Reduction", "Water Efficiency", False, 6, "water"),
        ("EAp1", "Fundamental Energy Performance", "Energy & Atmosphere", True, None, "energy"),
        ("EAc1", "Optimize Energy Performance", "Energy & Atmosphere", False, 18, "energy"),
        ("EAc2", "Building-Level Energy Metering", "Energy & Atmosphere", False, 1, "energy"),
        ("EAc3", "Building-Level Water Metering", "Energy & Atmosphere", False, 1, "water"),
        ("EAc4", "Enhanced Commissioning", "Energy & Atmosphere", False, 6, "commissioning"),
        ("EAc5", "Renewable Energy and Storage", "Energy & Atmosphere", False, 5, "carbon"),
        ("MRp1", "Material Disclosure and Optimization", "Materials & Resources", True, None, "materials"),
        ("MRc1", "Environmental Product Declarations", "Materials & Resources", False, 2, "materials"),
        ("MRc2", "Sourcing of Raw Materials", "Materials & Resources", False, 2, "materials"),
        ("MRc3", "Construction and Demolition Waste", "Materials & Resources", False, 2, "materials"),
        ("EQp1", "Minimum Indoor Air Quality Performance", "Indoor Environmental Quality", True, None, "iaq"),
        ("EQc1", "Enhanced Indoor Air Quality Strategies", "Indoor Environmental Quality", False, 2, "iaq"),
        ("EQc2", "Low-Emitting Materials", "Indoor Environmental Quality", False, 3, "low_emitting"),
        ("EQc3", "Daylight and Quality Views", "Indoor Environmental Quality", False, 3, "daylight"),
        ("INc1", "Innovation", "Innovation", False, 5, "innovation"),
        ("RPc1", "Regional Priority", "Regional Priority", False, 4, "regional"),
        ("CAc1", "Operational and Embodied Carbon", "Decarbonization", False, 8, "carbon"),
        ("HWc1", "Health and Wellbeing", "Health & Wellbeing", False, 4, "health"),
        ("CRc1", "Climate Resilience", "Resilience", False, 4, "resilience"),
    ]
    def module_root(self, version: str, family: str, adaptation: str) -> Path:
        return REGISTRY_ROOT / version / family / adaptation

    def list_credits(self, version: str, family: str, adaptation: str) -> list[CreditModule]:
        base = self.module_root(version, family, adaptation)
        modules = [self._load(path) for path in sorted(base.glob("*/credit.yaml"))] if base.exists() else []
        existing = {m.credit_id for m in modules}
        modules.extend(CreditModule(version, family, adaptation, cid, cid, name, category, prereq, points, module_type, "builtin/catalog", "heuristic_builtin", {"official_source_status": "heuristic_builtin", "requirement_summary": "Upload official rating-system materials before submission."}) for cid, name, category, prereq, points, module_type in self.BUILTIN_CATALOG if cid not in existing)
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
        base = self.module_root(version, family, adaptation)
        modules = [self._load(path) for path in sorted(base.glob("*/credit.yaml"))] if base.exists() else []
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
