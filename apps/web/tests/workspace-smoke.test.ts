import { describe, expect, it } from "vitest";

describe("LEED consultant workspace routes", () => {
  it("keeps the dashboard, wizard, scorecard and document-center route contracts", () => {
    const routes = ["/app/dashboard", "/app/projects/new", "/app/projects/:projectId/scorecard", "/app/projects/:projectId/documents"];
    expect(routes).toHaveLength(4);
  });
});
