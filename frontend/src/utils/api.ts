// src/utils/api.ts
import { getSessionId } from './session';

const isLocalDev =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const BASE_URL = isLocalDev
    ? ((import.meta as any).env?.VITE_API_URL ?? 'http://localhost:7860')
    : '';

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
    const existingHeaders = (options?.headers as Record<string, string>) ?? {};
    const res = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            'X-Session-ID': getSessionId(),
            ...existingHeaders,
        },
    });
    const data = await res.json();
    if (!res.ok) {
        const msg = (data as any)?.detail?.error || (data as any)?.error || `HTTP ${res.status}`;
        throw new Error(msg);
    }
    return data as T;
}