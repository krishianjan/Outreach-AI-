// src/utils/api.ts
// Single source of truth for the API base URL.
//
// Local dev  (localhost): calls http://localhost:7860
// Production (HF Spaces, etc.): calls same origin (empty string = relative URL)
//
// This means NO CORS issues in production and no config needed — it just works.

const isLocalDev =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const BASE_URL = isLocalDev
    ? ((import.meta as any).env?.VITE_API_URL ?? 'http://localhost:7860')
    : ''; // empty string = relative URL = same origin in production

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BASE_URL}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    const data = await res.json();
    if (!res.ok) {
        const msg =
            (data as any)?.detail?.error ||
            (data as any)?.error ||
            `HTTP ${res.status}`;
        throw new Error(msg);
    }
    return data as T;
}