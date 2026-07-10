"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../../../../lib/api";

export default function NewProject() {
  const router = useRouter();
  const [form, setForm] = useState({ name: "", location_city: "", location_country: "", building_type: "Office", gross_floor_area: "", leed_version: "v5", rating_family: "BDC", adaptation: "NC", target_certification: "Gold", current_phase: "concept" });
  const [error, setError] = useState("");
  const update = (key: string, value: string) => setForm((old) => ({ ...old, [key]: value }));
  async function submit(event: FormEvent) { event.preventDefault(); setError(""); try { const project = await api<{ id: string }>("/api/projects", { method: "POST", body: JSON.stringify({ ...form, gross_floor_area: form.gross_floor_area ? Number(form.gross_floor_area) : null }) }); router.push(`/app/projects/${project.id}/documents`); } catch (err) { setError(err instanceof Error ? err.message : "Unable to create project"); } }
  return <main className="shell"><h1>Project setup wizard</h1><p>Choose the rating version and pathway first; the assessment uses that registry.</p><form className="card form-grid" onSubmit={submit}>
    <label>Project name<input required value={form.name} onChange={(e) => update("name", e.target.value)} /></label>
    <label>Building type<input value={form.building_type} onChange={(e) => update("building_type", e.target.value)} /></label>
    <label>City<input value={form.location_city} onChange={(e) => update("location_city", e.target.value)} /></label>
    <label>Country<input value={form.location_country} onChange={(e) => update("location_country", e.target.value)} /></label>
    <label>Gross floor area (m²)<input type="number" min="0" value={form.gross_floor_area} onChange={(e) => update("gross_floor_area", e.target.value)} /></label>
    <label>LEED version<select value={form.leed_version} onChange={(e) => update("leed_version", e.target.value)}><option value="v4">v4</option><option value="v4_1">v4.1</option><option value="v5">v5</option></select></label>
    <label>Rating family<select value={form.rating_family} onChange={(e) => update("rating_family", e.target.value)}><option value="BDC">BD+C</option><option value="IDC">ID+C</option><option value="OM">O+M</option></select></label>
    <label>Adaptation<input value={form.adaptation} onChange={(e) => update("adaptation", e.target.value)} placeholder="NC / CI / EBOM" /></label>
    <label>Target certification<select value={form.target_certification} onChange={(e) => update("target_certification", e.target.value)}><option>Certified</option><option>Silver</option><option>Gold</option><option>Platinum</option></select></label>
    <label>Current phase<select value={form.current_phase} onChange={(e) => update("current_phase", e.target.value)}>{["concept","schematic_design","design_development","construction_documents","tender","construction","as_built","submission","comment_response"].map((x) => <option key={x}>{x}</option>)}</select></label>
    {error && <p className="error">{error}</p>}<button type="submit">Create project and upload evidence</button>
  </form></main>;
}
