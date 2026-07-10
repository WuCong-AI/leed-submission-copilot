from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


LeedVersion = Literal["v4", "v4_1", "v5"]
RatingFamily = Literal["BDC", "IDC", "OM"]
ProjectPhase = Literal["concept", "schematic_design", "design_development", "construction_documents", "tender", "construction", "as_built", "submission", "comment_response"]


class ProjectCreate(BaseModel):
    name: str
    location_country: str = ""
    location_city: str = ""
    address_text: str = ""
    building_type: str = "Other"
    gross_floor_area: float | None = None
    leed_version: LeedVersion
    rating_family: RatingFamily
    adaptation: str
    target_certification: Literal["Certified", "Silver", "Gold", "Platinum"]
    current_phase: ProjectPhase = "concept"
    project_boundary_description: str = ""
    organization_id: UUID | None = None


class ProjectSummary(ProjectCreate):
    id: UUID
    estimated_score: int | None = None
    high_risk_prerequisites: int = 0
    high_risk_credits: int = 0
    created_at: datetime


class CreditRegistryItem(BaseModel):
    credit_id: str
    credit_code: str
    credit_name: str
    category: str
    is_prerequisite: bool
    max_points: int | None = None
    module_type: str
    registry_path: str
    official_source_status: str


class ProjectCreditStatus(BaseModel):
    status: Literal["not_started", "pursuing", "likely", "at_risk", "achieved", "not_pursuing", "denied"]
    target_points: int | None = None
    estimated_points: int | None = None
    awarded_points: int | None = None
    risk_level: Literal["low", "medium", "high", "critical", "needs_official_source"] = "needs_official_source"
    responsible_discipline: str = "leed_consultant"
    notes: str = ""


class DocumentUpload(BaseModel):
    document_type: str = "other"
    phase: ProjectPhase = "concept"
    discipline: str = "other"
    related_credit_id: str | None = None


class EvidenceItem(BaseModel):
    credit_id: str
    evidence_type: str
    evidence_status: Literal["missing", "provided", "accepted", "rejected", "needs_review"]
    extracted_summary: str
    source_refs: list[dict] = Field(default_factory=list)
    confidence: float = 0.0


class ReviewFinding(BaseModel):
    credit_id: str | None = None
    phase: ProjectPhase
    severity: Literal["info", "low", "medium", "high", "critical"]
    finding_type: Literal["compliant", "likely_compliant", "gap", "contradiction", "missing_evidence", "not_applicable", "needs_official_source"]
    finding_text: str
    recommended_action: str
    responsible_discipline: str
    evidence_refs: list[dict] = Field(default_factory=list)
    confidence: float = 0.0


class StageReviewRequest(BaseModel):
    phase: ProjectPhase
    selected_credit_ids: list[str] = Field(default_factory=list)
    document_ids: list[UUID] = Field(default_factory=list)
    review_depth: Literal["quick", "standard", "detailed"] = "standard"


class StageReviewResponse(BaseModel):
    project_summary: str
    findings: list[ReviewFinding]
    discipline_actions: dict[str, list[str]]
    assumptions: list[str]


class PreAssessmentRequest(BaseModel):
    known_constraints: list[str] = Field(default_factory=list)
    document_ids: list[UUID] = Field(default_factory=list)


class PreAssessmentResponse(BaseModel):
    rating_system_fit: str
    prerequisite_risk_matrix: list[ReviewFinding]
    credit_feasibility: list[dict]
    conservative_score: int | None = None
    target_score: int | None = None
    stretch_score: int | None = None
    design_decisions_needed: list[str]
    missing_information: list[str]
    recommended_actions_by_discipline: dict[str, list[str]]
    assumptions: list[str]
    total_possible_points: int = 0
    evidence_points: int = 0
    certification: str = "Not enough evidence"
    automated_findings: list[dict] = Field(default_factory=list)


class SubmissionPacketResponse(BaseModel):
    credit_id: str
    narrative_markdown: str
    attachment_index: list[dict]
    evidence_manifest: list[EvidenceItem]
    missing_items: list[str]
    assumptions: list[str]
    reviewer_risk_report: dict


class CommentRiskResponse(BaseModel):
    credit_id: str
    risk_score: int = Field(ge=0, le=5)
    likely_comments: list[str]
    trigger_reasons: list[str]
    missing_evidence: list[str]
    recommended_fixes: list[str]
    confidence: float
    limitations: list[str]


class TenderRequirementResponse(BaseModel):
    credit_id: str
    package_name: str
    requirement_text: str
    responsible_party: str
    evidence_required: list[str]
    due_phase: str
    source_rule_refs: list[str]
    legal_review_required: bool = True


class AnalysisResponse(BaseModel):
    project_id: UUID
    total_possible_points: int
    evidence_points: int
    conservative_score: int
    target_score: int
    stretch_score: int
    certification: str
    confidence: float
    drawing_summary: dict = Field(default_factory=dict)
    credit_results: list[dict] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
