export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://leed-submission-copilot-api.onrender.com";

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      const response = await fetch(`${API_BASE}${path}`, { ...options, cache: "no-store", headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) } });
      if (response.ok) return response.json() as Promise<T>;
      const detail = await response.text();
      if (![502, 503, 504].includes(response.status) || attempt === 3) throw new Error(`${response.status}: ${detail}`);
      lastError = new Error(`${response.status}: ${detail}`);
    } catch (error) {
      lastError = error;
      if (attempt === 3 || (error instanceof Error && !/Failed to fetch|NetworkError|Load failed/i.test(error.message))) throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
  }
  throw lastError instanceof Error ? lastError : new Error("Network request failed");
}
