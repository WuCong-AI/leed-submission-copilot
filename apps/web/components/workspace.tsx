import Link from "next/link";

export function RiskBadge({ level = "needs_official_source" }: { level?: string }) { return <span className="tag warn">{level.replaceAll("_", " ")}</span>; }
export function EvidenceCitation({ file = "No cited evidence" }: { file?: string }) { return <small>Source: {file}</small>; }
export function ProjectCard({ name, version, family, phase }: { name: string; version: string; family: string; phase: string }) { return <article className="card"><h3>{name}</h3><p>{version} · {family} · {phase}</p><RiskBadge /></article>; }
export function CreditStatusBadge({ status }: { status: string }) { return <span className="tag">{status.replaceAll("_", " ")}</span>; }
export function MissingInformationChecklist() { return <div className="card"><h3>Missing information</h3><p className="warn">NEED_OFFICIAL_SOURCE: load official source data before using score thresholds.</p></div>; }
export function WorkspaceNav({ projectId = "demo" }: { projectId?: string }) { return <nav><Link href={`/app/projects/${projectId}/scorecard`}>Scorecard</Link>{" · "}<Link href={`/app/projects/${projectId}/documents`}>Documents</Link>{" · "}<Link href={`/app/projects/${projectId}/stage-review`}>Stage review</Link>{" · "}<Link href={`/app/projects/${projectId}/submission`}>Submission</Link>{" · "}<Link href={`/app/projects/${projectId}/comments`}>Comments</Link></nav>; }
