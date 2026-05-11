// src/utils/session.ts
// Generates a unique ID per browser tab session.
// Stored in sessionStorage — resets on every new tab/window open.
// This is what scopes all data (leads, activity, stats) to the current user.

const SESSION_KEY = 'outreach_sid';

export function getSessionId(): string {
    let sid = sessionStorage.getItem(SESSION_KEY);
    if (!sid) {
        // Generate UUID v4 (crypto.randomUUID preferred, fallback for older browsers)
        sid = typeof crypto !== 'undefined' && crypto.randomUUID
            ? crypto.randomUUID()
            : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
        sessionStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
}

export function clearSession(): void {
    // Remove all outreach-related session keys
    const keysToRemove: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key && (key.startsWith('os_') || key === SESSION_KEY)) {
            keysToRemove.push(key);
        }
    }
    keysToRemove.forEach(k => sessionStorage.removeItem(k));
}