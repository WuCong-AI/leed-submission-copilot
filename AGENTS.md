# LEED Submission Copilot Rules

- Never hard-code LEED requirements in business logic. Load them from `data/rating_systems/`.
- Every assessment, finding, submission packet, and comment-risk result needs source references or an explicit assumption/`NEED_OFFICIAL_SOURCE` marker.
- Keep LEED v4.1 and v5, plus BD+C, ID+C, and O+M workflows separate. O+M is an operational-performance and policy workflow.
- Use structured JSON/Pydantic models before generating human-readable text.
- AI-style text must include confidence and missing-evidence warnings. Never fabricate evidence, thresholds, or points.
- Precedent material supports patterns and gaps only; never reproduce source submission text verbatim.
- Tests cover registry loading, project setup, scorecards, documents, reviews, submission packets, and comment risk.
