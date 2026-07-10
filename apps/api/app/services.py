from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from packages.leed_core.registry import CreditModule, RegistryService
from .schemas import (
    CommentRiskResponse, DocumentUpload, EvidenceItem, PreAssessmentRequest,
    PreAssessmentResponse, ProjectCreate, ProjectCreditStatus, ProjectSummary,
    ReviewFinding, StageReviewRequest, StageReviewResponse, SubmissionPacketResponse,
    TenderRequirementResponse,
)


def registry_key(project: ProjectCreate | ProjectSummary) -> tuple[str, str, str]:
    return project.leed_version, project.rating_family, project.adaptation


class MemoryStore:
    """MVP persistence adapter. Replace behind this interface with SQLAlchemy repositories."""
    def __init__(self, registry: RegistryService | None = None) -> None:
        self.registry = registry or RegistryService()
        self.projects: dict[UUID, ProjectSummary] = {}
        self.scorecards: dict[UUID, dict[str, ProjectCreditStatus]] = {}
        self.documents: dict[UUID, list[dict]] = {}
        self.chunks: dict[UUID, list[dict]] = {}

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
        return status

    async def add_document(self, project_id: UUID, upload: UploadFile, metadata: DocumentUpload) -> dict:
        content = await upload.read()
        doc_id = uuid4()
        filename = Path(upload.filename or "upload.bin").name
        record = {"id": doc_id, "filename": filename, "document_type": metadata.document_type, "phase": metadata.phase, "discipline": metadata.discipline, "related_credit_id": metadata.related_credit_id, "processing_status": "processed", "size_bytes": len(content)}
        self.documents[project_id].append(record)
        text = content.decode("utf-8", errors="replace") if filename.lower().endswith((".txt", ".md", ".csv")) else "NEED_OFFICIAL_SOURCE: parser fallback did not extract this binary document."
        self.chunks[doc_id] = [{"chunk_index": 0, "chunk_text": text[:10000], "source_refs": [{"filename": filename, "chunk_index": 0}]}]
        return record

    def evidence(self, project_id: UUID, credit_id: str) -> list[EvidenceItem]:
        documents = [doc for doc in self.documents[project_id] if doc.get("related_credit_id") in {None, credit_id}]
        if not documents:
            return [EvidenceItem(credit_id=credit_id, evidence_type="registry evidence schema", evidence_status="missing", extracted_summary="No uploaded evidence matched this credit.", confidence=0.0)]
        return [EvidenceItem(credit_id=credit_id, evidence_type="uploaded document", evidence_status="needs_review", extracted_summary=f"{doc['filename']} is available for structured evidence review.", source_refs=[{"document_id": str(doc['id']), "filename": doc['filename']}], confidence=0.35) for doc in documents]

    def pre_assessment(self, project_id: UUID, request: PreAssessmentRequest) -> PreAssessmentResponse:
        project = self.project(project_id)
        entries = self.scorecard(project_id)
        feasibility = [{"credit_id": item["credit"].credit_id, "credit_name": item["credit"].credit_name, "possible_points": item["credit"].max_points, "status": item["status"].status, "official_source_status": item["credit"].official_source_status} for item in entries]
        prereq_findings = [self._source_finding(item["credit"], project.current_phase) for item in entries if item["credit"].is_prerequisite]
        return PreAssessmentResponse(rating_system_fit=f"Registry path: {project.leed_version}/{project.rating_family}/{project.adaptation}", prerequisite_risk_matrix=prereq_findings, credit_feasibility=feasibility, design_decisions_needed=["Confirm rating-system registration path against official project materials."], missing_information=["NEED_OFFICIAL_SOURCE: official thresholds and path options are not loaded for one or more modules."], recommended_actions_by_discipline={"leed_consultant": ["Load approved official registry source data before relying on score estimates."]}, assumptions=["No LEED thresholds or points are inferred outside the registry."])

    def stage_review(self, project_id: UUID, request: StageReviewRequest) -> StageReviewResponse:
        project = self.project(project_id)
        credit_ids = request.selected_credit_ids or [item["credit"].credit_id for item in self.scorecard(project_id)]
        findings: list[ReviewFinding] = []
        for credit_id in credit_ids:
            module = self.registry.get_credit(*registry_key(project), credit_id)
            evidence = self.evidence(project_id, credit_id)
            findings.append(ReviewFinding(credit_id=credit_id, phase=request.phase, severity="high" if evidence[0].evidence_status == "missing" else "medium", finding_type="missing_evidence" if evidence[0].evidence_status == "missing" else "needs_official_source", finding_text="Required evidence is not verified against an official registry source." if evidence[0].evidence_status == "missing" else "Evidence is uploaded but needs registry-based validation.", recommended_action="Assign the evidence owner and validate against evidence_schema.json after official fields are supplied.", responsible_discipline="leed_consultant", evidence_refs=evidence[0].source_refs, confidence=evidence[0].confidence))
        return StageReviewResponse(project_summary=f"{len(findings)} registry-driven findings for {request.phase}.", findings=findings, discipline_actions={"leed_consultant": [finding.recommended_action for finding in findings]}, assumptions=["Deterministic MVP; no LLM or unverified LEED threshold is used."])

    def submission_packet(self, project_id: UUID, credit_id: str) -> SubmissionPacketResponse:
        evidence = self.evidence(project_id, credit_id)
        missing = [item.evidence_type for item in evidence if item.evidence_status == "missing"]
        return SubmissionPacketResponse(credit_id=credit_id, narrative_markdown=f"# {credit_id}\n\n## Evidence-backed narrative\nNEED_OFFICIAL_SOURCE: narrative structure is ready, but no official requirement text or accepted evidence is available.", attachment_index=[ref for item in evidence for ref in item.source_refs], evidence_manifest=evidence, missing_items=missing, assumptions=["No missing evidence was fabricated."], reviewer_risk_report=self.comment_risk(project_id, credit_id).model_dump())

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
