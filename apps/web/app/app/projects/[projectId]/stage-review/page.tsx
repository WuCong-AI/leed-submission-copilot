"use client";

import { useEffect, useState } from "react";
import { WorkspaceNav } from "../../../../../components/workspace";
import { api } from "../../../../../lib/api";

const phases = ["concept", "schematic_design", "design_development", "construction_documents", "tender", "construction", "as_built", "submission", "comment_response"];
type Finding = { credit_id?: string; phase: string; severity: string; finding_type: string; finding_text: string; recommended_action: string; responsible_discipline: string; evidence_refs?: { filename?: string }[]; confidence: number };
type Review = { project_summary: string; findings: Finding[]; discipline_actions: Record<string, string[]>; assumptions: string[] };

export default function Review({ params }: { params: Promise<{ projectId: string }> }) {
  const [projectId, setProjectId] = useState("");
  const [phase, setPhase] = useState("concept");
  const [depth, setDepth] = useState("standard");
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => { params.then(({ projectId: id }) => setProjectId(id)); }, [params]);
  async function runReview() {
    if (!projectId) return;
    setBusy(true); setMessage("");
    try { setReview(await api<Review>(`/api/projects/${projectId}/stage-review`, { method: "POST", body: JSON.stringify({ phase, review_depth: depth, selected_credit_ids: [], document_ids: [] }) })); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Stage review failed"); }
    finally { setBusy(false); }
  }
  return <main className="shell"><WorkspaceNav projectId={projectId}/><h1>Stage review</h1><p>Evidence-based review for the selected LEED version and rating family. Official-source notes are shown separately from project evidence gaps.</p><section className="card"><div className="actions"><label>Review phase<select value={phase} onChange={(e) => setPhase(e.target.value)}>{phases.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select></label><label>Review depth<select value={depth} onChange={(e) => setDepth(e.target.value)}><option value="quick">quick</option><option value="standard">standard</option><option value="detailed">detailed</option></select></label><button onClick={runReview} disabled={busy || !projectId}>{busy ? "Reviewing…" : "Run stage review"}</button></div>{message && <p className="warn">{message}</p>}</section>{review && <section className="results"><div className="card"><h2>{review.project_summary}</h2><p>These findings are indicative and must be checked against the official LEED reference owned by the project team.</p></div><h2>Review findings ({review.findings.length})</h2>{review.findings.map((finding, index) => <article className={`finding ${finding.severity}`} key={`${finding.credit_id || "general"}-${index}`}><b>{finding.credit_id || "Project-level"}</b> <span className="tag">{finding.severity} · {finding.finding_type.replaceAll("_", " ")}</span><p>{finding.finding_text}</p><p><b>Corrective action:</b> {finding.recommended_action}</p><small>Responsible: {finding.responsible_discipline} · confidence {Math.round(finding.confidence * 100)}%</small>{finding.evidence_refs?.map((ref, refIndex) => <small key={refIndex}> · Evidence: {ref.filename || "uploaded document"}</small>)}</article>)}<div className="card"><h3>Methodology note</h3>{review.assumptions.map((item) => <p key={item}>{item}</p>)}</div></section>}</main>;
}
