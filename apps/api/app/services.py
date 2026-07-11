from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from packages.leed_core.registry import CreditModule, RegistryService
from .schemas import (
    CommentRiskResponse, DesignGuideResponse, DocumentUpload, EvidenceItem, PreAssessmentRequest,
    PreAssessmentResponse, ProjectCreate, ProjectCreditStatus, ProjectSummary,
    ReviewFinding, StageReviewRequest, StageReviewResponse, SubmissionPacketResponse,
    TenderRequirementResponse,
)
from .ingestion import extract_upload, extract_upload_path
from .assessment import RULES, assess


def registry_key(project: ProjectCreate | ProjectSummary) -> tuple[str, str, str]:
    return project.leed_version, project.rating_family, project.adaptation


class MemoryStore:
    """MVP persistence adapter. Replace behind this interface with SQLAlchemy repositories."""
    def __init__(self, registry: RegistryService | None = None) -> None:
        self.registry = registry or RegistryService()
        self.data_root = Path(os.getenv("LOCAL_STORAGE_PATH", "/workspace/data/uploads"))
        self.raw_root = self.data_root / "raw"
        self.staging_root = self.data_root / "staging"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_root / "state.json"
        self._state_lock = threading.RLock()
        self.projects: dict[UUID, ProjectSummary] = {}
        self.scorecards: dict[UUID, dict[str, ProjectCreditStatus]] = {}
        self.documents: dict[UUID, list[dict]] = {}
        self.chunks: dict[UUID, list[dict]] = {}
        self.analyses: dict[UUID, dict] = {}
        self.upload_sessions: dict[str, dict] = {}
        self.upload_jobs: dict[str, dict] = {}
        self._load_state()

    def _save_state(self) -> None:
        """Persist the MVP state so Render restarts do not erase projects and evidence index."""
        with self._state_lock:
            payload = {
                "projects": [project.model_dump(mode="json") for project in self.projects.values()],
                "scorecards": {str(project_id): {credit_id: status.model_dump(mode="json") for credit_id, status in rows.items()} for project_id, rows in self.scorecards.items()},
                "documents": {str(project_id): [{**record, "id": str(record["id"])} for record in rows] for project_id, rows in self.documents.items()},
                "chunks": {str(document_id): rows for document_id, rows in self.chunks.items()},
                "analyses": {str(project_id): result for project_id, result in self.analyses.items()},
                "upload_jobs": self.upload_jobs,
                "upload_sessions": self.upload_sessions,
            }
            temp_path = self.state_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
            temp_path.replace(self.state_path)

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.projects = {UUID(item["id"]): ProjectSummary.model_validate(item) for item in payload.get("projects", [])}
            self.scorecards = {UUID(project_id): {credit_id: ProjectCreditStatus.model_validate(status) for credit_id, status in rows.items()} for project_id, rows in payload.get("scorecards", {}).items()}
            self.documents = {UUID(project_id): [{**record, "id": UUID(record["id"])} for record in rows] for project_id, rows in payload.get("documents", {}).items()}
            # Remove the old low-memory warning from documents indexed by the
            # previous release; the metadata-only path is an intentional,
            # successful processing mode rather than a document error.
            for rows in self.documents.values():
                for record in rows:
                    record["warnings"] = [warning for warning in record.get("warnings", []) if not warning.startswith("Content extraction skipped for a large archive member")]
            self.chunks = {UUID(document_id): rows for document_id, rows in payload.get("chunks", {}).items()}
            self.analyses = {UUID(project_id): result for project_id, result in payload.get("analyses", {}).items()}
            self.upload_jobs = {
                str(job_id): {**job, "project_id": UUID(job["project_id"]) if isinstance(job.get("project_id"), str) else job.get("project_id")}
                for job_id, job in payload.get("upload_jobs", {}).items()
            }
            self.upload_sessions = {
                str(session_id): {**session, "project_id": UUID(session["project_id"]) if isinstance(session.get("project_id"), str) else session.get("project_id")}
                for session_id, session in payload.get("upload_sessions", {}).items()
            }
            # A process cannot resume a Python background task after a restart.
            # Keep the job visible to the UI and explain the safe next action.
            for job in self.upload_jobs.values():
                if job.get("status") in {"queued", "processing"}:
                    job.update({"status": "error", "error": "Upload processing was interrupted by a service restart. The archive remains stored; please retry this upload."})
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # A corrupt state file should not prevent the API from starting.
            self.projects, self.scorecards, self.documents, self.chunks, self.analyses = {}, {}, {}, {}, {}
            self.upload_jobs, self.upload_sessions = {}, {}

    def persist(self) -> None:
        self._save_state()

    def create_project(self, input: ProjectCreate) -> ProjectSummary:
        project = ProjectSummary(**input.model_dump(), id=uuid4(), created_at=datetime.now(timezone.utc))
        self.projects[project.id] = project
        self.documents[project.id] = []
        modules = self.registry.list_credits(*registry_key(project))
        self.scorecards[project.id] = {
            module.credit_id: ProjectCreditStatus(
                status="not_started",
                risk_level="needs_official_source" if module.max_points is None else "medium",
            ) for module in modules
        }
        self._save_state()
        return project

    def project(self, project_id: UUID) -> ProjectSummary:
        return self.projects[project_id]

    def scorecard(self, project_id: UUID) -> list[dict]:
        project = self.project(project_id)
        modules = self.registry.list_credits(*registry_key(project))
        statuses = self.scorecards[project_id]
        return [{"credit": module, "status": statuses[module.credit_id]} for module in modules]

    def update_credit(self, project_id: UUID, credit_id: str, status: ProjectCreditStatus) -> ProjectCreditStatus:
        self.registry.get_credit(*registry_key(self.project(project_id)), credit_id)
        self.scorecards[project_id][credit_id] = status
        self._save_state()
        return status

    async def add_document(self, project_id: UUID, upload: UploadFile, metadata: DocumentUpload) -> dict:
        content = await upload.read()
        filename = Path(upload.filename or "upload.bin").name
        raw_path = self.raw_root / str(project_id) / f"{uuid4()}-{filename}"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(content)
        extracted = extract_upload(filename, content, upload.content_type)
        return self._store_extracted(project_id, extracted, metadata, filename.lower().endswith(".zip"), str(raw_path))

    def add_document_path(self, project_id: UUID, filename: str, path: str, metadata: DocumentUpload, raw_path: str | None = None) -> dict:
        if raw_path is None:
            raw_file = self.raw_root / str(project_id) / f"{uuid4()}-{Path(filename).name}"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "rb") as source, open(raw_file, "wb") as target:
                while chunk := source.read(8 * 1024 * 1024):
                    target.write(chunk)
            raw_path = str(raw_file)
        extracted = extract_upload_path(filename, path)
        return self._store_extracted(project_id, extracted, metadata, filename.lower().endswith(".zip"), raw_path)

    def process_upload_job(self, job_id: str, project_id: UUID, filename: str, path: str, metadata: DocumentUpload) -> None:
        job = self.upload_jobs.get(job_id)
        if job is None:
            return
        job["status"] = "processing"
        self._save_state()
        try:
            result = self.add_document_path(project_id, filename, path, metadata)
            job.update({"status": "complete", **result})
        except Exception as exc:  # keep the worker alive and expose a useful UI error
            job.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            self._save_state()
            try:
                os.remove(path)
            except OSError:
                pass

    def _store_extracted(self, project_id: UUID, extracted: list[dict], metadata: DocumentUpload, archive: bool = False, storage_path: str | None = None) -> dict:
        created = []
        for item in extracted:
            doc_id = uuid4()
            record = {"id": doc_id, "filename": item["filename"], "archive_member": item.get("archive_member"), "document_type": metadata.document_type, "phase": metadata.phase, "discipline": metadata.discipline, "related_credit_id": metadata.related_credit_id, "processing_status": "processed", "size_bytes": item["size_bytes"], "mime_type": item["mime_type"], "extension": item["extension"], "page_count": item["page_count"], "warnings": item["warnings"], "drawing": item["drawing"], "text_preview": item["text"][:1500], "storage_path": storage_path}
            self.documents[project_id].append(record)
            self.chunks[doc_id] = [{"chunk_index": 0, "chunk_text": item["text"][:10000], "source_refs": [{"filename": item["filename"], "archive_member": item.get("archive_member"), "document_id": str(doc_id)}]}]
            created.append(record)
        self._save_state()
        return {"uploaded": created, "count": len(created), "archive": archive}

    def evidence(self, project_id: UUID, credit_id: str) -> list[EvidenceItem]:
        documents = [doc for doc in self.documents[project_id] if doc.get("related_credit_id") in {None, credit_id}]
        if not documents:
            return [EvidenceItem(credit_id=credit_id, evidence_type="registry evidence schema", evidence_status="missing", extracted_summary="No uploaded evidence matched this credit.", confidence=0.0)]
        return [EvidenceItem(credit_id=credit_id, evidence_type="uploaded document", evidence_status="needs_review", extracted_summary=f"{doc['filename']} is available for structured evidence review.", source_refs=[{"document_id": str(doc['id']), "filename": doc['filename']}], confidence=0.35) for doc in documents]

    def pre_assessment(self, project_id: UUID, request: PreAssessmentRequest) -> PreAssessmentResponse:
        project = self.project(project_id)
        entries = self.scorecard(project_id)
        analysis = self.analyze(project_id, request.document_ids or None)
        feasibility = [{"credit_id": item["credit"].credit_id, "credit_name": item["credit"].credit_name, "possible_points": item["credit"].max_points, "status": item["status"].status, "official_source_status": item["credit"].official_source_status} for item in entries]
        prereq_findings = [self._source_finding(item["credit"], project.current_phase) for item in entries if item["credit"].is_prerequisite]
        return PreAssessmentResponse(rating_system_fit=f"Registry path: {project.leed_version}/{project.rating_family}/{project.adaptation}", prerequisite_risk_matrix=prereq_findings, credit_feasibility=feasibility, conservative_score=analysis["conservative_score"], target_score=analysis["target_score"], stretch_score=analysis["stretch_score"], design_decisions_needed=[f"Review {len([f for f in analysis['findings'] if f['severity'] in {'high','critical'}])} high-risk findings before submission."], missing_information=["NEED_OFFICIAL_SOURCE: official thresholds must be verified before certification.", *analysis["limitations"]], recommended_actions_by_discipline={"leed_consultant": [f["recommended_action"] for f in analysis["findings"][:8]]}, assumptions=["Automated result is indicative and must be checked against the selected official rating system."], total_possible_points=analysis["total_possible_points"], evidence_points=analysis["evidence_points"], certification=analysis["certification"], automated_findings=analysis["findings"])

    def analyze(self, project_id: UUID, document_ids: list[UUID] | None = None) -> dict:
        project = self.project(project_id)
        documents = self.documents[project_id]
        if document_ids:
            allowed = set(document_ids)
            documents = [d for d in documents if d["id"] in allowed]
        modules = self.registry.list_credits(*registry_key(project))
        result = assess(modules, documents, project.target_certification)
        result["project_id"] = project_id
        result["drawing_summary"] = {"document_count": len(documents), "drawing_candidates": sum(1 for d in documents if d.get("drawing", {}).get("is_drawing_candidate")), "disciplines": sorted({discipline for d in documents for discipline in d.get("drawing", {}).get("disciplines", [])}), "sheet_labels": sorted({sheet for d in documents for sheet in d.get("drawing", {}).get("sheet_labels", [])})[:100], "warnings": [warning for d in documents for warning in d.get("warnings", [])]}
        self.analyses[project_id] = result
        return result

    def stage_review(self, project_id: UUID, request: StageReviewRequest) -> StageReviewResponse:
        project = self.project(project_id)
        credit_ids = request.selected_credit_ids or [item["credit"].credit_id for item in self.scorecard(project_id)]
        findings: list[ReviewFinding] = []
        for credit_id in credit_ids:
            module = self.registry.get_credit(*registry_key(project), credit_id)
            docs = self.documents[project_id]
            requirements, actions = self._submission_requirement_review(module, docs)
            pattern, default_action, default_owner = RULES.get(module.module_type, (module.credit_name.lower(), f"Map the uploaded evidence to the {module.credit_name} supporting-document list.", "leed_consultant"))
            tokens = [token.strip().lower() for token in pattern.split("|")]
            matched = [doc for doc in docs if any(token in re.sub(r"[_./\\-]+", " ", f"{doc.get('filename', '')} {doc.get('text_preview', '')} {' '.join(doc.get('drawing', {}).get('keyword_hits', []))}").lower() for token in tokens)]
            missing_requirements = [item for item in requirements if item["status"] == "missing"]
            source_requirements = [item for item in requirements if item["status"] == "needs_official_source"]
            refs = [{"document_id": str(doc["id"]), "filename": doc["filename"]} for doc in matched[:8]]
            if not matched:
                finding_type = "missing_evidence"
                severity = "high" if module.is_prerequisite else "medium"
                finding_text = f"No {module.credit_name}-specific indicator was found in the uploaded filenames, text previews or drawing keywords. Expected evidence: {', '.join(item['requirement'] for item in requirements) or default_action}"
                action = actions[0] if actions else default_action
                confidence = 0.15
            elif missing_requirements:
                finding_type = "gap"
                severity = "high" if module.is_prerequisite else "medium"
                finding_text = f"Matched {len(matched)} relevant file(s), but the supporting-document list is incomplete: {', '.join(item['requirement'] for item in missing_requirements)}."
                action = " ".join(item["modification_comment"] for item in missing_requirements)
                confidence = 0.55
            else:
                finding_type = "needs_official_source" if source_requirements else "likely_compliant"
                severity = "medium" if source_requirements else "low"
                finding_text = f"Matched {len(matched)} file(s) to {module.credit_name}: {', '.join(doc['filename'] for doc in matched[:4])}. Verify every required field and cross-credit scope before submission."
                action = " ".join(item["modification_comment"] for item in source_requirements or requirements) or default_action
                confidence = 0.68 if source_requirements else 0.78
            findings.append(ReviewFinding(credit_id=credit_id, phase=request.phase, severity=severity, finding_type=finding_type, finding_text=finding_text, recommended_action=action, responsible_discipline=default_owner, evidence_refs=refs, confidence=confidence))
        return StageReviewResponse(project_summary=f"{len(findings)} registry-driven findings for {request.phase}.", findings=findings, discipline_actions={"leed_consultant": [finding.recommended_action for finding in findings]}, assumptions=["Deterministic MVP; no LLM or unverified LEED threshold is used."])

    def design_guide(self, project_id: UUID, phase: str = "concept") -> DesignGuideResponse:
        project = self.project(project_id)
        modules = self.registry.list_credits(*registry_key(project))
        available = {module.module_type for module in modules}
        pillars = [
            {"id": "decarbonization", "label": "Decarbonization", "color": "#0f766e", "objective": "Set an operational and embodied-carbon budget before fixing the concept.", "decisions": ["Define energy model baseline and carbon boundary", "Compare passive design, electrification, renewables and material options"], "deliverables": ["Concept energy/carbon brief", "Embodied-carbon/LCA assumptions register"], "owners": ["architect", "mep_engineer", "leed_consultant"]},
            {"id": "health", "label": "Health & Wellbeing", "color": "#7c3aed", "objective": "Protect indoor air quality, daylight, thermal comfort and occupant experience from the first layout.", "decisions": ["Reserve ventilation, filtration and entryway-control zones", "Set daylight, glare, acoustics and low-emitting material targets"], "deliverables": ["IAQ strategy diagram", "Daylight/comfort concept targets", "Low-emitting materials schedule"], "owners": ["architect", "mep_engineer"]},
            {"id": "biodiversity", "label": "Biodiversity & Ecosystems", "color": "#15803d", "objective": "Avoid ecological harm and use the site concept to restore habitat and climate resilience.", "decisions": ["Map existing habitat, soil, water and heat-island risks", "Set native planting, stormwater and light-pollution principles"], "deliverables": ["Site ecology constraints plan", "Landscape and stormwater concept"], "owners": ["landscape_architect", "civil_engineer"]},
        ]
        sequence = [
            {"step": 1, "title": "Set project priorities", "description": "Confirm owner goals, certification target, site boundary, floor area and carbon/health/ecology priorities.", "evidence": ["Owner project requirements", "Integrative workshop agenda and decisions"], "owner": "leed_consultant", "status": "start"},
            {"step": 2, "title": "Lock site and climate response", "description": "Complete site, transport, ecology, flood, heat and stormwater constraints before massing is fixed.", "evidence": ["Site assessment", "Climate-risk and ecology plan", "Transport and parking assumptions"], "owner": "architect", "status": "next"},
            {"step": 3, "title": "Test passive and energy options", "description": "Compare orientation, envelope, shading, HVAC, electrification, renewables, metering and energy-model baselines.", "evidence": ["Concept energy model", "Energy/carbon option matrix", "Commissioning strategy"], "owner": "mep_engineer", "status": "next"},
            {"step": 4, "title": "Coordinate water and materials", "description": "Set water budgets, fixture strategy, irrigation, material transparency, EPD and circularity requirements.", "evidence": ["Water balance", "Outline specification", "EPD/material data request"], "owner": "mep_engineer / contractor", "status": "next"},
            {"step": 5, "title": "Protect occupant wellbeing", "description": "Translate IAQ, daylight, thermal comfort, acoustics and low-emitting goals into room layouts and specifications.", "evidence": ["IAQ zoning", "Daylight targets", "Low-emitting schedule"], "owner": "architect", "status": "next"},
            {"step": 6, "title": "Issue the concept decision log", "description": "Record each option, selected design, owner, assumptions, unresolved risk and required next-phase evidence.", "evidence": ["Concept LEED decision log", "Responsibility matrix", "Open-issues register"], "owner": "leed_consultant", "status": "gate"},
        ]
        deliverables = []
        for pillar in pillars:
            deliverables.extend({"pillar": pillar["label"], "name": item, "owner": ", ".join(pillar["owners"]), "phase": phase, "status": "required"} for item in pillar["deliverables"])
        return DesignGuideResponse(project_id=project_id, phase=phase, title=f"{project.name} · Concept LEED design guide", summary=f"{project.leed_version} {project.rating_family}/{project.adaptation} · target {project.target_certification}. Use this sequence to make design decisions before schematic design.", pillars=pillars, decision_sequence=sequence, concept_deliverables=deliverables)

    def submission_packet(self, project_id: UUID, credit_id: str) -> SubmissionPacketResponse:
        project = self.project(project_id)
        module = self.registry.get_credit(*registry_key(project), credit_id)
        evidence = self.evidence(project_id, credit_id)
        requirement_review, corrective_actions = self._submission_requirement_review(module, self.documents[project_id])
        missing = [item["requirement"] for item in requirement_review if item["status"] == "missing"]
        source_gaps = [item["requirement"] for item in requirement_review if item["status"] == "needs_official_source"]
        return SubmissionPacketResponse(credit_id=credit_id, narrative_markdown=f"# {credit_id}\n\n## Evidence-backed narrative\nDraft prepared for {module.credit_name}. Each claim must be mapped to the requirement review below before formal submission.", attachment_index=[ref for item in evidence for ref in item.source_refs], evidence_manifest=evidence, missing_items=missing + source_gaps, assumptions=[f"Review path: {project.leed_version}/{project.rating_family}/{project.adaptation}.", "Automated checks are evidence-matching controls, not a GBCI/USGBC certification decision."], reviewer_risk_report=self.comment_risk(project_id, credit_id).model_dump(), requirement_review=requirement_review, corrective_action_plan=corrective_actions)

    def _submission_requirement_review(self, module: CreditModule, documents: list[dict]) -> tuple[list[dict], list[str]]:
        """Compare uploaded evidence to the credit's supporting-document schema."""
        requirements: list[dict] = []
        repo_root = Path(__file__).resolve().parents[3]
        schema_path = repo_root / "data" / module.registry_path / "evidence_schema.json"
        if schema_path.exists():
            try:
                requirements = json.loads(schema_path.read_text(encoding="utf-8")).get("required", [])
            except (OSError, ValueError, TypeError):
                requirements = []
        if not requirements:
            defaults = {
                "integrative_process": ("integrative workshop record", ["pdf", "docx", "xlsx"], ["workshop", "integrative", "meeting", "agenda", "coordination"], "leed_consultant"),
                "location_transportation": ("location and transportation plan", ["pdf", "dwg", "dxf", "xlsx"], ["site", "parking", "transit", "transport", "bike", "ev"], "architect"),
                "site": ("site assessment and sustainable sites plan", ["pdf", "dwg", "dxf", "xlsx"], ["site", "landscape", "stormwater", "grading", "habitat"], "landscape_architect"),
                "biodiversity": ("biodiversity and ecosystem conservation plan", ["pdf", "dwg", "dxf", "xlsx"], ["biodiversity", "ecosystem", "habitat", "planting", "native", "landscape"], "landscape_architect"),
                "water": ("water use calculation and fixture schedule", ["pdf", "xlsx", "docx"], ["water", "fixture", "plumbing", "irrigation", "meter"], "mep_engineer"),
                "energy": ("energy model and commissioning evidence", ["pdf", "xlsx", "docx"], ["energy", "model", "hvac", "commission", "meter", "chiller"], "mep_engineer"),
                "carbon": ("operational and embodied carbon calculation", ["pdf", "xlsx", "docx"], ["carbon", "lca", "embodied", "energy", "epd"], "leed_consultant"),
                "materials": ("materials inventory and manufacturer EPDs", ["pdf", "xlsx", "docx"], ["epd", "material", "product", "lca", "recycled"], "contractor"),
                "iaq": ("indoor air quality and ventilation documentation", ["pdf", "dwg", "xlsx", "docx"], ["iaq", "air", "ventilation", "hvac", "filter", "smoke"], "mep_engineer"),
                "low_emitting": ("low-emitting materials schedule and VOC evidence", ["pdf", "xlsx", "docx"], ["low-emitting", "voc", "material", "adhesive", "paint"], "architect"),
                "daylight": ("daylighting simulation and annotated plans", ["pdf", "xlsx", "dwg", "dxf"], ["daylight", "glare", "simulation", "window", "floor plan"], "architect"),
                "commissioning": ("commissioning plan, report and issues log", ["pdf", "docx", "xlsx"], ["commission", "cx", "issues log", "functional"], "commissioning_agent"),
                "health": ("health and wellbeing assessment", ["pdf", "xlsx", "docx"], ["health", "wellbeing", "occupant", "survey", "iaq"], "leed_consultant"),
                "resilience": ("climate risk and resilience assessment", ["pdf", "xlsx", "docx"], ["resilience", "climate", "flood", "heat", "hazard"], "architect"),
            }
            default = defaults.get(module.module_type, (f"{module.credit_name} supporting documentation", ["pdf", "docx", "xlsx"], [module.credit_name.lower()], "leed_consultant"))
            requirements = [{"evidence_type": default[0], "accepted_file_types": default[1], "required_fields": ["official clause reference", "project scope", "calculation or narrative conclusion"], "required_phase": "submission", "responsible_discipline": default[3], "_keywords": default[2]}]
        review: list[dict] = []
        actions: list[str] = []
        for requirement in requirements:
            name = str(requirement.get("evidence_type", "supporting document"))
            accepted = [str(item).lower().lstrip(".") for item in requirement.get("accepted_file_types", [])]
            fields = [str(item) for item in requirement.get("required_fields", [])]
            keywords = requirement.get("_keywords") or [token for token in re.findall(r"[a-z0-9]+", name.lower()) if len(token) > 3]
            matches = []
            for document in documents:
                haystack = re.sub(r"[_./\\-]+", " ", f"{document.get('filename', '')} {document.get('text_preview', '')}").lower()
                extension = str(document.get("extension", "")).lower().lstrip(".")
                if extension in accepted and any(keyword.lower() in haystack for keyword in keywords):
                    matches.append(document)
            official_required = any("NEED_OFFICIAL_SOURCE" in field or "official" in field.lower() for field in fields)
            status = "missing" if not matches else ("needs_official_source" if official_required else "provided")
            matched_files = [{"document_id": str(document["id"]), "filename": document["filename"]} for document in matches]
            if status == "missing":
                rule_action = RULES.get(module.module_type, ("", "", ""))[1]
                action = f"{rule_action} Add {name}; accepted types: {', '.join(accepted) or 'project evidence'}. Include: {', '.join(fields) or 'scope, calculation, conclusion'}; responsible party: {requirement.get('responsible_discipline', 'leed_consultant')}."
                steps = [f"Create or export a {', '.join(accepted) or 'project evidence'} file named with the credit ID and evidence type.", f"Add a dedicated section/table for: {', '.join(fields) or 'project scope, calculation, conclusion'}.", "Add page, drawing-sheet or calculation-cell references for every claim.", f"Assign final review to {requirement.get('responsible_discipline', 'leed_consultant')} before submission."]
            elif status == "needs_official_source":
                rule_action = RULES.get(module.module_type, ("", "", ""))[1]
                action = f"{rule_action} For {name}, cite the official {module.leed_version} {module.rating_family}/{module.adaptation} clause and map each required field ({', '.join(fields)}) to a page, sheet or calculation cell."
                steps = [f"Insert the official {module.leed_version} {module.rating_family}/{module.adaptation} credit/prerequisite reference in the narrative.", f"Map each field ({', '.join(fields)}) to a page, sheet or calculation cell.", "Reconcile the narrative, drawings, calculations and scorecard scope before upload."]
            else:
                rule_action = RULES.get(module.module_type, ("", "", ""))[1]
                action = f"{rule_action} Revise {name} to add explicit clause citation and page/sheet references for: {', '.join(fields) or 'scope and conclusion'}."
                steps = [f"Add the official clause reference to {name}.", f"Add page/sheet/cell citations for: {', '.join(fields) or 'scope and conclusion'}.", "Check consistency with project boundary, area and related credits."]
            review.append({"requirement": name, "status": status, "required_phase": requirement.get("required_phase", "submission"), "accepted_file_types": accepted, "required_fields": fields, "validation_rules": requirement.get("validation_rules", []), "responsible_discipline": requirement.get("responsible_discipline", "leed_consultant"), "matched_files": matched_files, "modification_comment": action, "specific_modification_steps": steps})
            actions.append(action)
        return review, actions

    def comment_risk(self, project_id: UUID, credit_id: str) -> CommentRiskResponse:
        evidence = self.evidence(project_id, credit_id)
        missing = [item.evidence_type for item in evidence if item.evidence_status == "missing"]
        return CommentRiskResponse(credit_id=credit_id, risk_score=5 if missing else 3, likely_comments=["Provide the applicable official form, calculation, and supporting evidence."], trigger_reasons=["NEED_OFFICIAL_SOURCE or unvalidated evidence."], missing_evidence=missing, recommended_fixes=["Load official registry fields and map each attachment to the evidence schema."], confidence=0.7, limitations=["Prediction is deterministic and not a GBCI/USGBC review decision."])

    def tender(self, project_id: UUID, credit_id: str, package_name: str) -> TenderRequirementResponse:
        module = self.registry.get_credit(*registry_key(self.project(project_id)), credit_id)
        return TenderRequirementResponse(credit_id=credit_id, package_name=package_name, requirement_text="NEED_OFFICIAL_SOURCE: technical tender requirement draft awaits approved registry requirement data.", responsible_party="contractor", evidence_required=["Registry evidence_schema.json must be completed from official source material."], due_phase="tender", source_rule_refs=[module.registry_path], legal_review_required=True)

    @staticmethod
    def _source_finding(module: CreditModule, phase: str) -> ReviewFinding:
        return ReviewFinding(credit_id=module.credit_id, phase=phase, severity="high", finding_type="needs_official_source", finding_text="Official prerequisite requirement is not loaded in the registry.", recommended_action="Add user-provided official source data before treating this prerequisite as satisfied.", responsible_discipline="leed_consultant", confidence=1.0)
