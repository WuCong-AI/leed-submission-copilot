from __future__ import annotations

from uuid import UUID, uuid4
import os
import tempfile

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from packages.leed_core.registry import RegistryService
from .schemas import (
    AnalysisResponse, CommentRiskResponse, DocumentUpload, PreAssessmentRequest, PreAssessmentResponse,
    ProjectCreate, ProjectCreditStatus, ProjectSummary, StageReviewRequest,
    StageReviewResponse, SubmissionPacketResponse, TenderRequirementResponse,
)
from .services import MemoryStore, registry_key
from .seed import seed_demo_projects


app = FastAPI(title="LEED Submission Copilot API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["*"])
registry = RegistryService()
store = MemoryStore(registry)


def get_project(project_id: UUID) -> ProjectSummary:
    try:
        return store.project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": "mvp-memory-store", "registry_root": str(registry.module_root("v5", "BDC", "NC"))}


@app.post("/api/demo/seed", response_model=list[ProjectSummary])
def seed_demo() -> list[ProjectSummary]:
    return seed_demo_projects(store)


@app.post("/api/projects", response_model=ProjectSummary)
def create_project(input: ProjectCreate) -> ProjectSummary:
    if not registry.list_credits(*registry_key(input)):
        raise HTTPException(status_code=422, detail="No registry modules exist for this version/family/adaptation")
    return store.create_project(input)


@app.get("/api/projects", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    return list(store.projects.values())


@app.get("/api/projects/{project_id}", response_model=ProjectSummary)
def project(project_id: UUID) -> ProjectSummary:
    return get_project(project_id)


@app.get("/api/projects/{project_id}/summary")
def project_summary(project_id: UUID) -> dict:
    item = get_project(project_id)
    return {"project": item, "scorecard": store.scorecard(project_id), "document_count": len(store.documents[project_id])}


@app.get("/api/projects/{project_id}/scorecard")
def scorecard(project_id: UUID) -> list[dict]:
    get_project(project_id)
    return [{"credit": {"credit_id": row["credit"].credit_id, "credit_code": row["credit"].credit_code, "credit_name": row["credit"].credit_name, "category": row["credit"].category, "is_prerequisite": row["credit"].is_prerequisite, "max_points": row["credit"].max_points, "module_type": row["credit"].module_type, "registry_path": row["credit"].registry_path, "official_source_status": row["credit"].official_source_status}, "status": row["status"]} for row in store.scorecard(project_id)]


@app.patch("/api/projects/{project_id}/credits/{credit_id}", response_model=ProjectCreditStatus)
def update_credit(project_id: UUID, credit_id: str, input: ProjectCreditStatus) -> ProjectCreditStatus:
    get_project(project_id)
    try:
        return store.update_credit(project_id, credit_id, input)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Credit not found in this registry") from exc


@app.get("/api/registry/{version}/{family}/{adaptation}")
def get_registry(version: str, family: str, adaptation: str) -> dict:
    return registry.load_registry(version, family, adaptation)


@app.get("/api/registry/{version}/{family}/{adaptation}/credits")
def list_registry_credits(version: str, family: str, adaptation: str) -> list[dict]:
    return [module.__dict__ for module in registry.list_credits(version, family, adaptation)]


@app.get("/api/registry/{version}/{family}/{adaptation}/credits/{credit_id}")
def registry_credit(version: str, family: str, adaptation: str, credit_id: str) -> dict:
    try:
        return registry.get_credit(version, family, adaptation, credit_id).__dict__
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/registry/validate")
def validate_registry(version: str = Query(...), family: str = Query(...), adaptation: str = Query(...)) -> dict:
    return registry.validate_registry(version, family, adaptation)


@app.post("/api/projects/{project_id}/documents/upload")
async def upload_document(project_id: UUID, file: UploadFile = File(...), document_type: str = "other", phase: str = "concept", discipline: str = "other", related_credit_id: str | None = None) -> dict:
    get_project(project_id)
    return await store.add_document(project_id, file, DocumentUpload(document_type=document_type, phase=phase, discipline=discipline, related_credit_id=related_credit_id))


@app.post("/api/projects/{project_id}/documents/upload-batch")
async def upload_documents(project_id: UUID, files: list[UploadFile] = File(...), document_type: str = "other", phase: str = "concept", discipline: str = "other", related_credit_id: str | None = None) -> dict:
    get_project(project_id)
    uploaded = []
    for file in files:
        uploaded.append(await store.add_document(project_id, file, DocumentUpload(document_type=document_type, phase=phase, discipline=discipline, related_credit_id=related_credit_id)))
    return {"files": uploaded, "count": sum(item.get("count", 0) for item in uploaded)}


@app.post("/api/projects/{project_id}/documents/upload-chunk")
async def upload_chunk(project_id: UUID, background_tasks: BackgroundTasks, chunk: UploadFile = File(...), upload_id: str = "", filename: str = "upload.zip", chunk_index: int = 0, total_chunks: int = 1, document_type: str = "other", phase: str = "concept", discipline: str = "other", related_credit_id: str | None = None) -> dict:
    """Append an upload chunk and process the archive only after the final chunk arrives."""
    get_project(project_id)
    if total_chunks < 1 or chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=422, detail="Invalid chunk index")
    payload = await chunk.read()
    if len(payload) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Chunk exceeds 16 MB")
    session_id = upload_id or str(uuid4())
    session = store.upload_sessions.get(session_id)
    if session is None:
        path = os.path.join(store.staging_root, f"leed-upload-{session_id}.part")
        session = {"path": path, "filename": os.path.basename(filename), "next": 0, "total": total_chunks, "project_id": project_id}
        store.upload_sessions[session_id] = session
    if session["project_id"] != project_id or session["total"] != total_chunks:
        raise HTTPException(status_code=409, detail=f"Upload session {session_id} does not match this project or file")
    # A response can be lost after the server writes a chunk. Treat a retry of
    # an already accepted chunk as an acknowledgement instead of appending it
    # a second time (which used to surface as Failed to fetch in the browser).
    if session.get("complete") and session.get("job_id"):
        return {"upload_id": session_id, "complete": True, "processing": True, "job_id": session["job_id"], "uploaded": [], "count": 0}
    if chunk_index < session["next"]:
        return {"upload_id": session_id, "complete": False, "received_chunks": session["next"], "total_chunks": total_chunks}
    if chunk_index != session["next"]:
        raise HTTPException(status_code=409, detail=f"Expected chunk {session['next']}")
    with open(session["path"], "ab") as handle:
        handle.write(payload)
    session["next"] += 1
    store.persist()
    if session["next"] < total_chunks:
        return {"upload_id": session_id, "complete": False, "received_chunks": session["next"], "total_chunks": total_chunks}
    metadata = DocumentUpload(document_type=document_type, phase=phase, discipline=discipline, related_credit_id=related_credit_id)
    job_id = str(uuid4())
    store.upload_jobs[job_id] = {"project_id": project_id, "status": "queued", "filename": session["filename"], "uploaded": [], "count": 0}
    store.persist()
    background_tasks.add_task(store.process_upload_job, job_id, project_id, session["filename"], session["path"], metadata)
    # Keep a small completed-session marker so a retry of the final request
    # returns the original job rather than creating a second archive.
    session["complete"] = True
    session["job_id"] = job_id
    return {"upload_id": session_id, "complete": True, "processing": True, "job_id": job_id, "uploaded": [], "count": 0}


@app.get("/api/projects/{project_id}/documents/upload-status/{job_id}")
def upload_status(project_id: UUID, job_id: str) -> dict:
    get_project(project_id)
    job = store.upload_jobs.get(job_id)
    if job is None or job.get("project_id") != project_id:
        # A status poll must not turn a transient restart into a browser
        # `Failed to fetch`. Return a structured terminal state instead.
        return {"status": "error", "error": "Upload job is no longer available. Please retry the archive upload."}
    return {key: value for key, value in job.items() if key != "project_id"}


@app.get("/api/projects/{project_id}/documents")
def documents(project_id: UUID) -> list[dict]:
    get_project(project_id)
    return store.documents[project_id]


@app.get("/api/documents/{document_id}")
def document(document_id: UUID) -> dict:
    for records in store.documents.values():
        for record in records:
            if record["id"] == document_id:
                return {**record, "chunks": store.chunks.get(document_id, [])}
    raise HTTPException(status_code=404, detail="Document not found")


@app.post("/api/documents/{document_id}/process")
def process_document(document_id: UUID) -> dict:
    return document(document_id)


@app.post("/api/projects/{project_id}/pre-assessment", response_model=PreAssessmentResponse)
def pre_assessment(project_id: UUID, request: PreAssessmentRequest) -> PreAssessmentResponse:
    get_project(project_id)
    return store.pre_assessment(project_id, request)


@app.post("/api/projects/{project_id}/analyze", response_model=AnalysisResponse)
def analyze_project(project_id: UUID, request: PreAssessmentRequest | None = None) -> dict:
    get_project(project_id)
    return store.analyze(project_id, request.document_ids if request else None)


@app.get("/api/projects/{project_id}/analysis", response_model=AnalysisResponse)
def latest_analysis(project_id: UUID) -> dict:
    get_project(project_id)
    return store.analyses.get(project_id) or store.analyze(project_id)


@app.post("/api/projects/{project_id}/stage-review", response_model=StageReviewResponse)
def stage_review(project_id: UUID, request: StageReviewRequest) -> StageReviewResponse:
    get_project(project_id)
    return store.stage_review(project_id, request)


@app.post("/api/projects/{project_id}/credits/{credit_id}/review", response_model=StageReviewResponse)
def credit_review(project_id: UUID, credit_id: str, request: StageReviewRequest) -> StageReviewResponse:
    request.selected_credit_ids = [credit_id]
    return stage_review(project_id, request)


@app.post("/api/projects/{project_id}/generate-tender", response_model=list[TenderRequirementResponse])
def generate_tender(project_id: UUID, credit_ids: list[str], package_name: str = "General") -> list[TenderRequirementResponse]:
    get_project(project_id)
    return [store.tender(project_id, credit_id, package_name) for credit_id in credit_ids]


@app.post("/api/projects/{project_id}/credits/{credit_id}/generate-tender", response_model=TenderRequirementResponse)
def credit_tender(project_id: UUID, credit_id: str, package_name: str = "General") -> TenderRequirementResponse:
    get_project(project_id)
    return store.tender(project_id, credit_id, package_name)


@app.post("/api/projects/{project_id}/credits/{credit_id}/submission-packet", response_model=SubmissionPacketResponse)
def submission_packet(project_id: UUID, credit_id: str) -> SubmissionPacketResponse:
    get_project(project_id)
    return store.submission_packet(project_id, credit_id)


@app.post("/api/projects/{project_id}/credits/{credit_id}/comment-risk", response_model=CommentRiskResponse)
def comment_risk(project_id: UUID, credit_id: str) -> CommentRiskResponse:
    get_project(project_id)
    return store.comment_risk(project_id, credit_id)


@app.get("/api/projects/{project_id}/credits/{credit_id}/precedents")
def precedents(project_id: UUID, credit_id: str) -> dict:
    get_project(project_id)
    return {"items": [], "limitations": ["No precedent database is loaded. Import redacted precedent metadata and chunks; source text is never returned verbatim."]}


@app.post("/api/precedents/import")
def import_precedent() -> dict:
    return {"status": "placeholder", "warning": "MVP accepts metadata only until persistent storage and redaction workflow are configured."}
