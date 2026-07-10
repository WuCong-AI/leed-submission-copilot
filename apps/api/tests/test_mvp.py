from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from packages.leed_core.registry import RegistryService
from apps.api.app.schemas import PreAssessmentRequest, ProjectCreate, StageReviewRequest
from apps.api.app.services import MemoryStore
from fastapi.testclient import TestClient
from apps.api.app.main import app


def test_registry_modules_have_full_contract_files():
    service = RegistryService()
    result = service.validate_registry("v5", "BDC", "NC")
    assert result["valid"]
    assert result["credit_count"] == 1


def test_project_setup_scorecard_and_non_fabricated_preassessment():
    store = MemoryStore()
    project = store.create_project(ProjectCreate(name="Demo", leed_version="v5", rating_family="BDC", adaptation="NC", target_certification="Gold"))
    scorecard = store.scorecard(project.id)
    assert scorecard[0]["credit"].max_points is None
    assessment = store.pre_assessment(project.id, PreAssessmentRequest())
    assert "NEED_OFFICIAL_SOURCE" in assessment.missing_information[0]


def test_stage_review_and_submission_packet_cite_or_warn():
    store = MemoryStore()
    project = store.create_project(ProjectCreate(name="Demo", leed_version="v4_1", rating_family="OM", adaptation="ExistingBuildings", target_certification="Silver"))
    review = store.stage_review(project.id, StageReviewRequest(phase="submission"))
    assert review.findings[0].finding_type in {"missing_evidence", "needs_official_source"}
    packet = store.submission_packet(project.id, "SSc1")
    assert packet.assumptions


def test_api_project_scorecard_and_review_routes():
    client = TestClient(app)
    assert len(client.post("/api/demo/seed").json()) == 3
    project_response = client.post("/api/projects", json={
        "name": "API demo", "leed_version": "v5", "rating_family": "BDC",
        "adaptation": "NC", "target_certification": "Gold",
    })
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    assert client.get(f"/api/projects/{project_id}/scorecard").status_code == 200
    review = client.post(f"/api/projects/{project_id}/stage-review", json={"phase": "concept"})
    assert review.status_code == 200
    assert review.json()["findings"][0]["finding_type"] == "missing_evidence"
