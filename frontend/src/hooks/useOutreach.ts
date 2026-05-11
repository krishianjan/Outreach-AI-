// src/hooks/useOutreach.ts
// All fetch() calls in one place. Every path and field name matches api_routes.py exactly.

import { BASE_URL } from '../utils/api';
export { BASE_URL };

// ── Shared fetch wrapper ────────────────────────────────────────────────────

async function api<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BASE_URL}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    const data = await res.json();
    if (!res.ok) {
        const msg =
            (data as any)?.detail?.error ||
            (data as any)?.error ||
            `Request failed: ${res.status}`;
        throw new Error(msg);
    }
    return data as T;
}

// ── Types matching backend response shapes ──────────────────────────────────

export interface Contact {
    email: string;         // alias for 'value' added by backend normalize
    value: string;         // original Hunter field
    first_name: string;
    last_name: string;
    position: string;
    verify_grade: string;  // 'HIGH' | 'MEDIUM' | 'LOW'  (uppercase from backend)
    hunter_score: number;
    confidence: number;
    source: string;
    type?: string;
    pattern?: string;
}

export interface VerifyResult {
    email: string;
    status: string;         // 'valid' | 'invalid' | 'catch_all' | 'blocked' | 'unknown'
    grade: string;          // 'HIGH' | 'MEDIUM' | 'LOW'
    confidence_score: number;
    send_recommended: boolean;
    is_catch_all: boolean;
    mail_provider: string | null;
    mx_host: string | null;
}

export interface DayEmail {
    subject: string;
    subject_variants: string[];
    body: string;
    ps_line?: string;
}

export interface Sequence {
    lead_id: number | null;
    model_used: string;
    day_0: DayEmail;
    day_3: DayEmail;
    day_7: DayEmail;
    day_14: DayEmail;
    success?: boolean;
    error?: string;
}

export interface Suggestion {
    icon: string;
    title: string;
    detail: string;
}

export interface SenderProfile {
    name: string;
    title: string;
    company: string;
    linkedin: string;
    extra: Record<string, string>;  // purpose-specific fields (skills, metrics, etc.)
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useOutreach() {

    const findDomain = (companyName: string, hint = '') =>
        api<{ domain: string; confidence: number; source: string }>('/api/find-domain', {
            method: 'POST',
            body: JSON.stringify({ company_name: companyName, category_hint: hint }),
        });

    const lookupContacts = (companyName: string, domain: string, purpose: string) =>
        api<{
            contacts: Contact[];
            domain: string;
            source: string;
            error?: string;
            needs_manual: boolean;
            purpose_target: string[];
        }>('/api/lookup', {
            method: 'POST',
            body: JSON.stringify({ company_name: companyName, domain, purpose }),
        });

    const verifyEmail = (email: string) =>
        api<VerifyResult>('/api/verify', {
            method: 'POST',
            body: JSON.stringify({ email }),
        });

    const addManualContact = (
        domain: string,
        firstName: string,
        lastName: string,
        position: string,
        purpose: string,
    ) =>
        api<{ contacts: Contact[] }>('/api/contacts/manual', {
            method: 'POST',
            body: JSON.stringify({
                domain,
                first_name: firstName,
                last_name: lastName,
                position,
                purpose,
            }),
        });

    const generateCampaign = (params: {
        email: string;
        domain: string;
        purpose: string;
        sender: Record<string, string>;
        preferred_model: string;
        first_name: string;
        last_name: string;
        position: string;
        rough_draft: string;
    }) =>
        api<Sequence>('/api/generate', {
            method: 'POST',
            body: JSON.stringify(params),
        });

    const enhanceEmail = (params: {
        rough_draft: string;
        purpose: string;
        contact_name: string;
        company: string;
        sender_name: string;
        sender_title: string;
        preferred_model: string;
    }) =>
        api<{
            subject_lines: string[];
            body: string;
            ps_line: string;
            improvements_made: string[];
            model_used: string;
        }>('/api/enhance', {
            method: 'POST',
            body: JSON.stringify(params),
        });

    const getSuggestions = (params: {
        purpose: string;
        company: string;
        sequence_preview: string;
    }) =>
        api<{ suggestions: Suggestion[]; model_used: string }>('/api/suggest', {
            method: 'POST',
            body: JSON.stringify(params),
        });

    const markSent = (leadId: number) =>
        api(`/api/leads/${leadId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status: 'sent' }),
        });

    const getStats = () =>
        api<{
            domains_cached: number;
            contacts_found: number;
            leads_total: number;
            emails_sent: number;
            hunter_credits_today: number;
            gemini_calls_today: number;
            hunter_daily_limit: number;
            gemini_daily_limit: number;
            dry_run: boolean;
        }>('/api/stats');

    return {
        findDomain,
        lookupContacts,
        verifyEmail,
        addManualContact,
        generateCampaign,
        enhanceEmail,
        getSuggestions,
        markSent,
        getStats,
    };
}