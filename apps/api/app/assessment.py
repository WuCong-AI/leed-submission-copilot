from __future__ import annotations

from typing import Any

from packages.leed_core.registry import CreditModule


RULES = {
    "iaq": ("outdoor air|fresh air|ventilation|ashrae 62|merv|co2 monitoring", "Provide ventilation calculations, outdoor-air schedules and commissioning records.", "MEP engineer"),
    "energy": ("energy model|eui|ashrae 90|baseline|energy optimization|chiller|commissioning", "Add an energy model, baseline comparison and signed commissioning scope.", "Energy modeller / MEP engineer"),
    "carbon": ("embodied carbon|operational carbon|lca|epd|renewable|solar|pv|refrigerant", "Quantify operational and embodied carbon and document the selected reduction strategy.", "LEED consultant / MEP engineer"),
    "materials": ("epd|environmental product|hpd|recycled content|fsc|responsibly sourced|lca", "Map product quantities to manufacturer EPD/HPD and chain-of-custody evidence.", "Architect / contractor"),
    "water": ("low-flow|low flow|fixture|irrigation|rainwater|water meter|potable water|water use", "Provide fixture schedules, water balance, irrigation design and meter locations.", "Plumbing / landscape engineer"),
    "site": ("site assessment|stormwater|heat island|green roof|permeable|transit|bike|parking|ev charging", "Attach site, transport, stormwater and heat-island calculations with drawings.", "Civil / landscape architect"),
    "biodiversity": ("native planting|habitat|biodiversity|ecosystem|tree canopy|pollinator|invasive", "Document habitat baseline, native planting schedule and ecosystem conservation actions.", "Landscape architect"),
    "daylight": ("daylight|sda|ase|glare|quality view|view factor", "Provide daylight simulation assumptions, model scope, plans and result plots.", "Architect / daylight modeller"),
    "low_emitting": ("low-emitting|low emitting|voc|formaldehyde|emission|greenguard", "Collect product cut sheets and VOC/emissions declarations for installed materials.", "Architect / contractor"),
    "commissioning": ("commissioning|cx|functional testing|systems manual|o&m", "Name the CxA and submit the commissioning plan, issue log and final report.", "Commissioning authority"),
    "health": ("wellbeing|thermal comfort|acoustic|biophilia|wellness|occupant survey", "Add health and wellbeing narrative, comfort criteria and verification evidence.", "Architect / IEQ consultant"),
    "resilience": ("climate risk|resilience|adaptation|flood|heat wave|wildfire|hazard", "Complete a climate-risk assessment and show design adaptations on drawings.", "Architect / civil engineer"),
    "innovation": ("innovation|pilot credit|exemplary performance|education program", "Define the innovation intent, measurable outcome and verification method.", "LEED consultant"),
    "regional": ("regional priority|local priority|regional material|local ecology", "Confirm applicable regional priorities against the official project location tool.", "LEED consultant"),
    "integrative_process": ("integrative process|charrette|option analysis|energy and water analysis", "Upload the integrative meeting record and documented option analysis.", "Owner / design team"),
}


def assess(modules: list[CreditModule], documents: list[dict[str, Any]], target: str = "Gold") -> dict[str, Any]:
    corpus = "\n".join(f"{d.get('filename','')} {d.get('text','')} {' '.join(d.get('drawing', {}).get('keyword_hits', []))}" for d in documents).lower()
    findings: list[dict] = []
    results: list[dict] = []
    evidence_points = 0
    possible = 0
    for module in modules:
        points = int(module.max_points or 0)
        possible += points
        pattern, action, owner = RULES.get(module.module_type, (module.credit_name.lower(), "Map this credit to official evidence requirements.", "LEED consultant"))
        import re
        hit = bool(re.search(pattern, corpus, flags=re.I))
        refs = [d["filename"] for d in documents if any(k.lower() in f"{d.get('filename','')} {d.get('text','')}".lower() for k in pattern.split("|"))][:5]
        status = "likely" if hit else "at_risk"
        confidence = 0.78 if hit else 0.12
        earned = points if hit else 0
        if hit:
            evidence_points += earned
            findings.append({"credit_id": module.credit_id, "severity": "info", "finding_type": "likely_compliant", "text": f"Evidence indicators found for {module.credit_name}.", "recommended_action": action, "responsible_discipline": owner, "evidence_refs": refs, "confidence": confidence})
        else:
            findings.append({"credit_id": module.credit_id, "severity": "high" if module.is_prerequisite else "medium", "finding_type": "missing_evidence", "text": f"No machine-readable evidence indicator found for {module.credit_name}.", "recommended_action": action, "responsible_discipline": owner, "evidence_refs": refs, "confidence": confidence})
        results.append({"credit_id": module.credit_id, "credit_code": module.credit_code, "credit_name": module.credit_name, "category": module.category, "is_prerequisite": module.is_prerequisite, "max_points": module.max_points, "status": status, "estimated_points": earned, "confidence": confidence, "official_source_status": module.official_source_status, "evidence_refs": refs})
    conservative = evidence_points
    target_score = min(possible, round(evidence_points * 1.2))
    stretch = min(possible, round(evidence_points * 1.45))
    score = target_score
    certification = "Platinum" if score >= 80 else "Gold" if score >= 60 else "Silver" if score >= 50 else "Certified" if score >= 40 else "Not enough evidence"
    return {"total_possible_points": possible, "evidence_points": evidence_points, "conservative_score": conservative, "target_score": target_score, "stretch_score": stretch, "certification": certification, "confidence": round(sum(r["confidence"] for r in results) / len(results), 2) if results else 0, "credit_results": results, "findings": findings, "limitations": ["Scores are indicative heuristics based on uploaded text, filenames and drawing metadata; they are not an official USGBC/GBCI review.", "Encrypted/scanned PDFs and native CAD/BIM geometry require an OCR or specialist parser to verify quantities and calculations."]}
