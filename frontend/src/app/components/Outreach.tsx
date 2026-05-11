// src/app/components/Outreach.tsx
// Complete rewrite — all real API calls, sessionStorage persistence across tab switches,
// full flow: company search → contacts → verify → compose → generate → edit → chat → ideas

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search, Copy, Check, ChevronDown, User, Sparkles, Shield, Send,
  RefreshCw, MessageSquare, Lightbulb, ChevronRight, Loader2,
  AlertCircle, X, Edit3,
} from 'lucide-react';
import { useOutreach, type Contact, type VerifyResult, type Sequence, type SenderProfile, type Suggestion } from '../../hooks/useOutreach';

// ─── Constants ────────────────────────────────────────────────────────────────

const PURPOSE_CHOICES = [
  { label: '💼 Founding Engineer Role', value: 'job_seeker' },
  { label: '🚀 Startup Collaboration', value: 'startup_founder' },
  { label: '💰 Investor Pitch', value: 'investor_pitch' },
  { label: '🤝 Referral Request', value: 'referral_request' },
  { label: '📈 B2B Sales', value: 'b2b_sales' },
  { label: '📨 Cold Outreach', value: 'cold_outreach' },
  { label: '🔗 Partnership', value: 'partnership' },
];

// Purpose-specific extra fields sent in the sender payload to the model
const PURPOSE_EXTRA: Record<string, Array<{ key: string; label: string; placeholder: string; multi?: boolean }>> = {
  job_seeker: [
    { key: 'skills', label: 'Your Key Skills', placeholder: 'Python, FastAPI, LLMs, React, system design...', multi: true },
    { key: 'projects', label: 'GitHub / Portfolio Links', placeholder: 'github.com/you/awesome-project  •  live-demo.com' },
  ],
  investor_pitch: [
    { key: 'fund', label: 'Your Fund / Firm', placeholder: 'YCombinator, Sequoia, angel...' },
    { key: 'portfolio', label: 'Notable Portfolio', placeholder: 'Airbnb (2009 seed), Stripe...' },
  ],
  b2b_sales: [
    { key: 'metrics', label: 'Key Metrics / Results', placeholder: '3x ROI in 90 days, 40% time saved...', multi: true },
    { key: 'customers', label: 'Notable Customers', placeholder: 'Companies already using your product' },
  ],
  referral_request: [
    { key: 'ask', label: "What You're Looking For", placeholder: 'Intro to their CTO, referral for Product role...' },
  ],
  startup_founder: [
    { key: 'project', label: 'Your Project / Startup', placeholder: 'What you\'re building in 1-2 sentences' },
  ],
  partnership: [
    { key: 'value_prop', label: 'Partnership Value', placeholder: 'What mutual value you bring to the table' },
  ],
};

const DAY_LABELS: Record<string, string> = {
  day_0: '📧 Day 0',
  day_3: '📅 Day 3',
  day_7: '🔔 Day 7',
  day_14: '🔚 Day 14',
};

const GRADE_MAP: Record<string, { color: string; bg: string; icon: string }> = {
  HIGH: { color: 'var(--color-emerald)', bg: 'rgba(16,185,129,0.09)', icon: '🟢' },
  MEDIUM: { color: 'var(--color-amber)', bg: 'rgba(245,158,11,0.09)', icon: '🟡' },
  LOW: { color: '#EF4444', bg: 'rgba(239,68,68,0.09)', icon: '🔴' },
};

const SENDER_FIELDS: Array<[keyof SenderProfile, string, string]> = [
  ['name', 'Your Name', 'Krishi Patel'],
  ['title', 'Your Title', 'AI/ML Engineer'],
  ['company', 'Company', 'Harvard Labs'],
  ['linkedin', 'LinkedIn URL', 'linkedin.com/in/...'],
];

const EMPTY_SENDER: SenderProfile = { name: '', title: '', company: '', linkedin: '', extra: {} };

const GEN_MESSAGES = [
  'Researching company…',
  'Analyzing purpose…',
  'Writing Day 0 email…',
  'Writing follow-ups…',
  'Polishing sequence…',
];

// ─── Session-state hook (survives tab switch via sessionStorage) ──────────────

function useSession<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void] {
  const [val, setVal] = useState<T>(() => {
    try {
      const s = sessionStorage.getItem(`os_${key}`);
      return s ? (JSON.parse(s) as T) : initial;
    } catch { return initial; }
  });

  const set = useCallback((v: T | ((p: T) => T)) => {
    setVal(prev => {
      const next = typeof v === 'function' ? (v as (p: T) => T)(prev) : v;
      try { sessionStorage.setItem(`os_${key}`, JSON.stringify(next)); } catch { }
      return next;
    });
  }, [key]);

  return [val, set];
}

function grade(g?: string | null) {
  return GRADE_MAP[(g ?? '').toUpperCase()] ?? GRADE_MAP.LOW;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Outreach() {
  const api = useOutreach();

  // ── Persisted across tab switches ──────────────────────────────────────────
  const [companyName, setCompanyName] = useSession<string>('company', '');
  const [domain, setDomain] = useSession<string>('domain', '');
  const [contacts, setContacts] = useSession<Contact[]>('contacts', []);
  const [selectedContact, setSelected] = useSession<Contact | null>('selected', null);
  const [purpose, setPurpose] = useSession<string>('purpose', 'job_seeker');
  const [sequence, setSequence] = useSession<Sequence | null>('sequence', null);

  // ── Ephemeral (ok to reset on tab switch) ──────────────────────────────────
  const [loadingFind, setLoadingFind] = useState(false);
  const [loadingGen, setLoadingGen] = useState(false);
  const [loadingVerify, setLoadingVerify] = useState(false);
  const [loadingEnhance, setLoadingEnhance] = useState<string | null>(null);
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadingSuggest, setLoadingSuggest] = useState(false);

  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [needsManual, setNeedsManual] = useState(false);
  const [manualFirst, setManualFirst] = useState('');
  const [manualLast, setManualLast] = useState('');
  const [manualRole, setManualRole] = useState('');

  const [activeDay, setActiveDay] = useState<'day_0' | 'day_3' | 'day_7' | 'day_14'>('day_0');
  const [editedBodies, setEditedBodies] = useState<Record<string, string>>({});
  const [chosenSubject, setChosenSubject] = useState<Record<string, number>>({});
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [chatMsgs, setChatMsgs] = useState<Array<{ role: 'user' | 'ai'; text: string }>>([]);
  const [chatInput, setChatInput] = useState('');
  const [genProgress, setGenProgress] = useState('');
  const [copied, setCopied] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null);

  const [roughDraft, setRoughDraft] = useState('');
  const [subjectHint, setSubjectHint] = useState('');
  const [preferred, setPreferred] = useState<'auto' | 'gemini_flash' | 'groq'>('auto');

  // ── Sender profile (localStorage — lasts across sessions) ──────────────────
  const [sender, setSender] = useState<SenderProfile>(() => {
    try { return JSON.parse(localStorage.getItem('outreach_sender') || 'null') ?? EMPTY_SENDER; }
    catch { return EMPTY_SENDER; }
  });
  useEffect(() => {
    try { localStorage.setItem('outreach_sender', JSON.stringify(sender)); } catch { }
  }, [sender]);

  const chatEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMsgs]);

  // ── Helpers ────────────────────────────────────────────────────────────────

  const toast_ = (msg: string, type: 'ok' | 'err' = 'ok') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).catch(() => { });
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  const dayEmail = (day: string) => sequence ? (sequence as Record<string, unknown>)[day] as (typeof sequence.day_0) | null : null;
  const currentDay = dayEmail(activeDay);
  const currentBody = editedBodies[activeDay] ?? currentDay?.body ?? '';
  const subjectIdx = chosenSubject[activeDay] ?? 0;
  const currentSubj = currentDay?.subject_variants?.[subjectIdx] ?? currentDay?.subject ?? '';
  const extraFields = PURPOSE_EXTRA[purpose] ?? [];

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleFind = async () => {
    if (!companyName.trim()) return;
    setLoadingFind(true);
    setContacts([]);
    setSelected(null);
    setNeedsManual(false);
    setVerifyResult(null);
    setSequence(null);
    try {
      const { domain: d } = await api.findDomain(companyName.trim());
      setDomain(d);
      const res = await api.lookupContacts(companyName.trim(), d, purpose);
      if (res.contacts?.length) {
        setContacts(res.contacts);
      } else {
        setNeedsManual(true);
      }
    } catch (e: unknown) {
      toast_((e as Error).message ?? 'Failed to find contacts', 'err');
    } finally {
      setLoadingFind(false);
    }
  };

  const handleClear = () => {
    // Clear all session state — start fresh search
    ['company', 'domain', 'contacts', 'selected', 'sequence'].forEach(k =>
      sessionStorage.removeItem(`os_${k}`)
    );
    setCompanyName('');
    setDomain('');
    setContacts([]);
    setSelected(null);
    setNeedsManual(false);
    setVerifyResult(null);
    setSequence(null);
    setSuggestions([]);
    setChatMsgs([]);
    setRoughDraft('');
    setSubjectHint('');
    setManualFirst(''); setManualLast(''); setManualRole('');
  };

  const handleManualAdd = async () => {
    if (!manualFirst.trim()) return;
    try {
      const res = await api.addManualContact(domain, manualFirst, manualLast, manualRole, purpose);
      setContacts(res.contacts ?? []);
      setNeedsManual(false);
    } catch (e: unknown) {
      toast_((e as Error).message ?? 'Failed to generate email variants', 'err');
    }
  };

  const handleVerify = async (c: Contact) => {
    setLoadingVerify(true);
    setVerifyResult(null);
    try {
      const r = await api.verifyEmail(c.email);
      setVerifyResult(r);
    } catch (e: unknown) {
      toast_('Verify failed: ' + (e as Error).message, 'err');
    } finally {
      setLoadingVerify(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedContact) return;
    setLoadingGen(true);
    setSequence(null);
    setSuggestions([]);
    setChatMsgs([]);

    let mi = 0;
    setGenProgress(GEN_MESSAGES[0]);
    const iv = setInterval(() => {
      mi = Math.min(mi + 1, GEN_MESSAGES.length - 1);
      setGenProgress(GEN_MESSAGES[mi]);
    }, 1800);

    try {
      const senderPayload: Record<string, string> = {
        name: sender.name,
        title: sender.title,
        company: sender.company,
        linkedin: sender.linkedin,
        ...(sender.extra ?? {}),
        ...(subjectHint ? { subject_hint: subjectHint } : {}),
      };

      const res = await api.generateCampaign({
        email: selectedContact.email,
        domain,
        purpose,
        sender: senderPayload,
        preferred_model: preferred,
        first_name: selectedContact.first_name,
        last_name: selectedContact.last_name,
        position: selectedContact.position,
        rough_draft: roughDraft,
      });

      setSequence(res);
      setActiveDay('day_0');
      setEditedBodies({
        day_0: res.day_0?.body ?? '',
        day_3: res.day_3?.body ?? '',
        day_7: res.day_7?.body ?? '',
        day_14: res.day_14?.body ?? '',
      });
      setChosenSubject({});
      fetchSuggestions(res);
    } catch (e: unknown) {
      toast_((e as Error).message ?? 'Generation failed — check API keys in Settings', 'err');
    } finally {
      clearInterval(iv);
      setGenProgress('');
      setLoadingGen(false);
    }
  };

  const fetchSuggestions = async (seq: Sequence) => {
    setLoadingSuggest(true);
    try {
      const res = await api.getSuggestions({
        purpose,
        company: domain,
        sequence_preview: seq.day_0?.body?.slice(0, 150) ?? '',
      });
      setSuggestions(res.suggestions ?? []);
    } catch {
      setSuggestions([]);
    } finally {
      setLoadingSuggest(false);
    }
  };

  const handleEnhance = async (day: string) => {
    if (!selectedContact) return;
    setLoadingEnhance(day);
    try {
      const res = await api.enhanceEmail({
        rough_draft: editedBodies[day] ?? '',
        purpose,
        contact_name: `${selectedContact.first_name} ${selectedContact.last_name}`.trim(),
        company: domain,
        sender_name: sender.name,
        sender_title: sender.title,
        preferred_model: preferred,
      });
      setEditedBodies(p => ({ ...p, [day]: res.body }));
      if (day === 'day_0' && res.subject_lines?.length) {
        setSequence(p => p ? {
          ...p,
          day_0: { ...p.day_0, subject_variants: res.subject_lines, subject: res.subject_lines[0] },
        } : p);
      }
      toast_('Email enhanced ✨');
    } catch (e: unknown) {
      toast_('Enhance failed: ' + (e as Error).message, 'err');
    } finally {
      setLoadingEnhance(null);
    }
  };

  const handleChat = async () => {
    const msg = chatInput.trim();
    if (!msg || !selectedContact) return;
    setChatInput('');
    setChatMsgs(p => [...p, { role: 'user', text: msg }]);
    setLoadingChat(true);
    try {
      const res = await api.enhanceEmail({
        rough_draft: `CURRENT EMAIL:\n${currentBody}\n\nUSER INSTRUCTION:\n${msg}`,
        purpose,
        contact_name: `${selectedContact.first_name} ${selectedContact.last_name}`.trim(),
        company: domain,
        sender_name: sender.name,
        sender_title: sender.title,
        preferred_model: preferred,
      });
      setEditedBodies(p => ({ ...p, [activeDay]: res.body }));
      setChatMsgs(p => [...p, { role: 'ai', text: `✅ Applied: "${msg}"` }]);
    } catch (e: unknown) {
      setChatMsgs(p => [...p, { role: 'ai', text: '❌ ' + (e as Error).message }]);
    } finally {
      setLoadingChat(false);
    }
  };

  const handleMarkSent = async () => {
    if (!sequence?.lead_id) { toast_('Generate a campaign first', 'err'); return; }
    try {
      await api.markSent(sequence.lead_id);
      toast_('Marked as sent — visible in Pipeline 📤');
    } catch (e: unknown) {
      toast_((e as Error).message, 'err');
    }
  };

  // ─── Shared style atoms ────────────────────────────────────────────────────
  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '9px 12px', borderRadius: 7,
    background: 'var(--bg-elevated)', border: '1px solid var(--border-custom)',
    color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', marginBottom: 4,
    color: 'var(--text-muted)', fontSize: 11,
  };
  const cardStyle: React.CSSProperties = {
    background: 'var(--bg-card)', borderRadius: 12,
    border: '1px solid var(--border-custom)', overflow: 'hidden',
    boxShadow: 'var(--shadow-sm)',
  };
  const cardHeaderStyle: React.CSSProperties = {
    padding: '13px 18px', borderBottom: '1px solid var(--border-light)',
    display: 'flex', alignItems: 'center', gap: 8,
    fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
  };

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ height: 'calc(100vh - 56px)', display: 'flex', position: 'relative', overflow: 'hidden' }}>

      {/* Toast */}
      {toast && (
        <div className="animate-slideInRight" style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 100,
          padding: '11px 18px', borderRadius: 10,
          background: toast.type === 'ok' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
          border: `1px solid ${toast.type === 'ok' ? 'var(--color-emerald)' : '#EF4444'}`,
          color: toast.type === 'ok' ? 'var(--color-emerald)' : '#EF4444',
          fontSize: 13, fontWeight: 600, backdropFilter: 'blur(8px)',
          boxShadow: 'var(--shadow-lg)',
        }}>
          {toast.msg}
        </div>
      )}

      {/* ═══════════════ LEFT PANEL ═══════════════════════════════════════════ */}
      <div style={{
        width: 400, flexShrink: 0, display: 'flex', flexDirection: 'column',
        overflowY: 'auto', background: 'var(--bg-card)',
        borderRight: '1px solid var(--border-custom)',
      }}>
        <div style={{ padding: '22px 20px 0' }}>

          {/* Step label */}
          <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
              color: 'var(--color-slate)', textTransform: 'uppercase'
            }}>
              Step 1 — Find Contacts
            </span>
            {contacts.length > 0 && (
              <span style={{ fontSize: 11, color: 'var(--color-emerald)', fontWeight: 600 }}>
                {contacts.length} found
              </span>
            )}
          </div>

          {/* Company input */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Company Name</label>
            <input
              value={companyName}
              onChange={e => setCompanyName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleFind()}
              placeholder="Stripe, Ramp, Cardinal AI…"
              style={inputStyle}
            />
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>We resolve the domain automatically</p>
          </div>

          {/* Purpose */}
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Outreach Purpose</label>
            <div style={{ position: 'relative' }}>
              <select
                value={purpose}
                onChange={e => setPurpose(e.target.value)}
                style={{ ...inputStyle, appearance: 'none', cursor: 'pointer' }}>
                {PURPOSE_CHOICES.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
              <ChevronDown size={15} style={{
                position: 'absolute', right: 10, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none',
              }} />
            </div>
          </div>

          {/* Find button */}
          <button
            onClick={handleFind}
            disabled={!companyName.trim() || loadingFind}
            style={{
              width: '100%', padding: '11px', borderRadius: 8, border: 'none',
              background: 'linear-gradient(135deg, #64748B 0%, #94A3B8 100%)',
              color: '#fff', fontSize: 14, fontWeight: 700, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              opacity: (!companyName.trim() || loadingFind) ? 0.55 : 1,
              marginBottom: contacts.length > 0 ? 8 : 20, transition: 'opacity 0.2s',
            }}>
            {loadingFind
              ? <><Loader2 size={16} className="animate-spin" />Finding contacts…</>
              : <><Search size={16} />Find Contacts</>}
          </button>

          {/* Clear / new search button — only show when there are results */}
          {(contacts.length > 0 || needsManual) && !loadingFind && (
            <button
              onClick={handleClear}
              style={{
                width: '100%', padding: '8px', borderRadius: 8, marginBottom: 16,
                border: '1px solid var(--border-custom)', background: 'transparent',
                color: 'var(--text-muted)', fontSize: 13, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-slate)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-muted)'; (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border-custom)'; }}>
              <X size={14} /> New Search
            </button>
          )}
        </div>

        {/* Skeleton */}
        {loadingFind && (
          <div style={{ padding: '0 20px 16px' }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{ padding: 14, borderRadius: 10, background: 'var(--bg-elevated)', marginBottom: 8 }}>
                <div style={{ display: 'flex', gap: 10 }}>
                  <div className="skeleton" style={{ width: 38, height: 38, borderRadius: '50%', flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div className="skeleton" style={{ height: 13, width: '60%', marginBottom: 6 }} />
                    <div className="skeleton" style={{ height: 11, width: '45%' }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Manual entry */}
        {needsManual && !loadingFind && (
          <div style={{ padding: '0 20px 16px' }}>
            <div style={{ ...cardStyle, padding: 16 }}>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>
                No public contacts found for <strong style={{ color: 'var(--color-slate)' }}>{domain}</strong>.
                Enter a name to generate email variants:
              </p>
              {([['First Name', manualFirst, setManualFirst], ['Last Name', manualLast, setManualLast], ['Their Role', manualRole, setManualRole]] as const).map(([ph, val, set]) => (
                <input key={ph as string} placeholder={ph as string} value={val as string}
                  onChange={e => (set as (v: string) => void)(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8 }} />
              ))}
              <button onClick={handleManualAdd} style={{
                width: '100%', padding: '9px', borderRadius: 7, border: 'none', cursor: 'pointer',
                background: 'var(--color-slate)', color: '#fff', fontSize: 13, fontWeight: 600,
              }}>
                Generate Email Variants
              </button>
            </div>
          </div>
        )}

        {/* Contact cards */}
        {!loadingFind && contacts.length > 0 && (
          <div style={{ padding: '0 20px 20px' }}>
            {contacts.map((c, i) => {
              const g = grade(c.verify_grade);
              const sel = selectedContact?.email === c.email;
              return (
                <div key={i}
                  onClick={() => { setSelected(c); setVerifyResult(null); }}
                  style={{
                    padding: 13, borderRadius: 10, cursor: 'pointer', marginBottom: 8,
                    background: sel ? 'rgba(100,116,139,0.06)' : 'var(--bg-elevated)',
                    border: `2px solid ${sel ? 'var(--color-slate)' : 'transparent'}`,
                    transition: 'all 0.15s',
                  }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <div style={{
                      width: 38, height: 38, borderRadius: '50%', flexShrink: 0,
                      background: 'linear-gradient(135deg, #64748B 0%, #94A3B8 100%)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: 15, fontWeight: 700,
                    }}>
                      {(c.first_name?.[0] ?? '?').toUpperCase()}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
                        <span style={{ color: 'var(--text-primary)', fontSize: 13, fontWeight: 600 }}>
                          {c.first_name} {c.last_name}
                        </span>
                        <span style={{
                          fontSize: 10, padding: '2px 7px', borderRadius: 10,
                          background: g.bg, color: g.color, fontWeight: 600, flexShrink: 0
                        }}>
                          {g.icon} {(c.verify_grade ?? 'LOW').toUpperCase()}
                        </span>
                      </div>
                      <p style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 4 }}>
                        {c.position || 'Unknown role'}
                      </p>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span style={{
                          color: 'var(--color-slate)', fontSize: 11, fontFamily: 'monospace',
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 185,
                        }}>
                          {c.email}
                        </span>
                        <button
                          onClick={e => { e.stopPropagation(); copy(c.email, `e${i}`); }}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, flexShrink: 0 }}>
                          {copied === `e${i}`
                            ? <Check size={12} style={{ color: 'var(--color-emerald)' }} />
                            : <Copy size={12} style={{ color: 'var(--text-muted)' }} />}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ═══════════════ RIGHT PANEL ══════════════════════════════════════════ */}
      <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg-primary)' }}>

        {/* Empty state */}
        {!selectedContact && (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{
                width: 72, height: 72, borderRadius: '50%', background: 'var(--bg-elevated)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 14px',
              }}>
                <User size={32} style={{ color: 'var(--text-muted)' }} />
              </div>
              <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>Select a contact to compose campaign</p>
              <p style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 5 }}>Results stay when you switch tabs</p>
            </div>
          </div>
        )}

        {selectedContact && (
          <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px 28px' }}>

            {/* ── Contact card ────────────────────────────────────────────── */}
            <div style={{ ...cardStyle, marginBottom: 18 }}>
              <div style={{ padding: '18px 20px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <div style={{
                      width: 50, height: 50, borderRadius: '50%', flexShrink: 0,
                      background: 'linear-gradient(135deg, #64748B 0%, #94A3B8 100%)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: '#fff', fontSize: 20, fontWeight: 700,
                    }}>
                      {(selectedContact.first_name?.[0] ?? '?').toUpperCase()}
                    </div>
                    <div>
                      <div style={{ color: 'var(--text-primary)', fontSize: 16, fontWeight: 700 }}>
                        {selectedContact.first_name} {selectedContact.last_name}
                      </div>
                      <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{selectedContact.position}</div>
                      <div style={{ color: 'var(--color-slate)', fontSize: 12, fontFamily: 'monospace', marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
                        {selectedContact.email}
                        <button onClick={() => copy(selectedContact.email, 'sel_email')}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}>
                          {copied === 'sel_email' ? <Check size={12} style={{ color: 'var(--color-emerald)' }} /> : <Copy size={12} style={{ color: 'var(--text-muted)' }} />}
                        </button>
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
                    <button onClick={() => setSelected(null)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer', fontSize: 12,
                        color: 'var(--text-muted)', fontWeight: 600, padding: '2px 6px'
                      }}>
                      Change
                    </button>
                    {!verifyResult && (
                      <button onClick={() => handleVerify(selectedContact)}
                        disabled={loadingVerify}
                        style={{
                          padding: '5px 12px', borderRadius: 6, border: '1px solid var(--border-custom)',
                          background: 'var(--bg-elevated)', color: 'var(--text-secondary)',
                          fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                          fontWeight: 500,
                        }}>
                        {loadingVerify
                          ? <><Loader2 size={12} className="animate-spin" />Verifying…</>
                          : <><Shield size={12} />Verify Email</>}
                      </button>
                    )}
                  </div>
                </div>

                {/* Verify result strip */}
                {verifyResult && (
                  <div className="animate-fadeIn" style={{
                    marginTop: 14, padding: '12px 14px', borderRadius: 8,
                    background: 'var(--bg-elevated)', border: '1px solid var(--border-light)',
                  }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 8 }}>
                      {[
                        ['Status', verifyResult.status?.replace(/_/g, ' ')],
                        ['Grade', `${grade(verifyResult.grade).icon} ${verifyResult.grade}`],
                        ['Provider', verifyResult.mail_provider ?? 'unknown'],
                        ['Confidence', `${Math.round((verifyResult.confidence_score ?? 0) * 100)}%`],
                      ].map(([label, val]) => (
                        <div key={label} style={{ textAlign: 'center' }}>
                          <div style={{
                            fontSize: 10, color: 'var(--text-muted)', marginBottom: 2,
                            textTransform: 'uppercase', letterSpacing: '0.05em'
                          }}>{label}</div>
                          <div style={{
                            fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
                            textTransform: 'capitalize'
                          }}>{val}</div>
                        </div>
                      ))}
                    </div>
                    {verifyResult.is_catch_all && (
                      <p style={{ fontSize: 11, color: 'var(--color-amber)', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <AlertCircle size={11} /> Catch-all domain — individual mailbox can't be confirmed
                      </p>
                    )}
                    <p style={{
                      fontSize: 11, marginTop: 4,
                      color: verifyResult.send_recommended ? 'var(--color-emerald)' : '#EF4444'
                    }}>
                      {verifyResult.send_recommended ? '✓ Safe to send' : '✗ Low confidence — use with caution'}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* ── COMPOSER (before generate) ────────────────────────────────── */}
            {!sequence && (
              <div className="animate-fadeIn" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

                <span style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                  color: 'var(--color-emerald)', textTransform: 'uppercase'
                }}>
                  Step 2 — Compose Campaign
                </span>

                {/* Sender details */}
                <div style={cardStyle}>
                  <div style={cardHeaderStyle}>
                    <User size={14} style={{ color: 'var(--color-slate)' }} />
                    Your Details
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
                      (auto-saved)
                    </span>
                  </div>
                  <div style={{ padding: '14px 18px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                      {SENDER_FIELDS.map(([key, label, ph]) => (
                        <div key={key}>
                          <label style={labelStyle}>{label}</label>
                          <input
                            value={sender[key] as string}
                            onChange={e => setSender(p => ({ ...p, [key]: e.target.value }))}
                            placeholder={ph}
                            style={inputStyle}
                          />
                        </div>
                      ))}
                    </div>

                    {/* Purpose-specific fields */}
                    {extraFields.length > 0 && (
                      <div style={{ paddingTop: 10, borderTop: '1px solid var(--border-light)' }}>
                        <p style={{ fontSize: 11, color: 'var(--color-slate)', marginBottom: 8, fontWeight: 600 }}>
                          {PURPOSE_CHOICES.find(p => p.value === purpose)?.label} context
                        </p>
                        {extraFields.map(f => (
                          <div key={f.key} style={{ marginBottom: 10 }}>
                            <label style={labelStyle}>{f.label}</label>
                            {f.multi ? (
                              <textarea rows={2} placeholder={f.placeholder}
                                value={sender.extra?.[f.key] ?? ''}
                                onChange={e => setSender(p => ({ ...p, extra: { ...p.extra, [f.key]: e.target.value } }))}
                                style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }} />
                            ) : (
                              <input placeholder={f.placeholder}
                                value={sender.extra?.[f.key] ?? ''}
                                onChange={e => setSender(p => ({ ...p, extra: { ...p.extra, [f.key]: e.target.value } }))}
                                style={inputStyle} />
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Draft & subject hint */}
                <div style={cardStyle}>
                  <div style={cardHeaderStyle}>
                    <Edit3 size={14} style={{ color: 'var(--color-amber)' }} />
                    Your Rough Draft
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
                      — model rewrites professionally
                    </span>
                  </div>
                  <div style={{ padding: '14px 18px' }}>
                    <div style={{ marginBottom: 12 }}>
                      <label style={labelStyle}>Subject idea (optional)</label>
                      <input
                        value={subjectHint}
                        onChange={e => setSubjectHint(e.target.value)}
                        placeholder="e.g. rebuilt your lead routing in 2 hours…"
                        style={inputStyle}
                      />
                    </div>
                    <label style={labelStyle}>
                      Rough draft / key points&nbsp;
                      <span style={{ color: 'var(--text-muted)' }}>(even 2 sentences helps the model write 10x better)</span>
                    </label>
                    <textarea
                      rows={4}
                      value={roughDraft}
                      onChange={e => setRoughDraft(e.target.value)}
                      placeholder={
                        purpose === 'job_seeker'
                          ? 'e.g. want to work there, built ml systems at harvard labs, shipped product 10k users, link to github…'
                          : purpose === 'investor_pitch'
                            ? 'e.g. hit 100k ARR in 3 months, b2b saas, looking for seed, strong retention…'
                            : purpose === 'b2b_sales'
                              ? 'e.g. we save ops teams 40% time, already used by 3 unicorns, want to show demo…'
                              : 'Describe your goal in rough words — model will rewrite professionally…'
                      }
                      style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.6, minHeight: 100 }}
                    />
                  </div>
                </div>

                {/* Model + Generate */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Model:</span>
                  {(['auto', 'gemini_flash', 'groq'] as const).map(m => (
                    <button key={m} onClick={() => setPreferred(m)} style={{
                      padding: '5px 13px', borderRadius: 6, border: 'none', cursor: 'pointer', fontSize: 12,
                      fontWeight: preferred === m ? 700 : 400,
                      background: preferred === m ? 'var(--color-slate)' : 'var(--bg-elevated)',
                      color: preferred === m ? '#fff' : 'var(--text-secondary)',
                      transition: 'all 0.15s',
                    }}>
                      {m === 'auto' ? '⚡ Auto' : m === 'gemini_flash' ? '🔵 Gemini' : '🟠 Groq'}
                    </button>
                  ))}
                </div>

                <button
                  onClick={handleGenerate}
                  disabled={loadingGen}
                  style={{
                    width: '100%', padding: '14px', borderRadius: 10, border: 'none', cursor: 'pointer',
                    background: loadingGen
                      ? 'var(--bg-elevated)'
                      : 'linear-gradient(135deg, #10B981 0%, #34D399 100%)',
                    color: loadingGen ? 'var(--text-muted)' : '#fff',
                    fontSize: 15, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                    transition: 'all 0.2s',
                  }}>
                  {loadingGen
                    ? <><Loader2 size={20} className="animate-spin" />{genProgress}</>
                    : <><Sparkles size={20} />Generate Full Campaign  (Day 0 · 3 · 7 · 14)</>}
                </button>
              </div>
            )}

            {/* ── EMAIL EDITOR (after generate) ─────────────────────────────── */}
            {sequence && (
              <div className="animate-fadeIn" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                    color: 'var(--color-emerald)', textTransform: 'uppercase'
                  }}>
                    ✨ Campaign ready · {sequence.model_used}
                  </span>
                  <button onClick={() => setSequence(null)}
                    style={{
                      fontSize: 12, color: 'var(--text-muted)', background: 'none', border: 'none',
                      cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4
                    }}>
                    <RefreshCw size={13} />Regenerate
                  </button>
                </div>

                {/* Day tabs */}
                <div style={{
                  display: 'flex', gap: 4, background: 'var(--bg-elevated)',
                  padding: 4, borderRadius: 10, border: '1px solid var(--border-custom)'
                }}>
                  {(['day_0', 'day_3', 'day_7', 'day_14'] as const).map(d => (
                    <button key={d} onClick={() => setActiveDay(d)} style={{
                      flex: 1, padding: '8px 4px', borderRadius: 7, border: 'none', cursor: 'pointer',
                      background: activeDay === d ? 'var(--bg-card)' : 'transparent',
                      color: activeDay === d ? 'var(--text-primary)' : 'var(--text-muted)',
                      fontSize: 12, fontWeight: activeDay === d ? 600 : 400,
                      boxShadow: activeDay === d ? 'var(--shadow-sm)' : 'none',
                      transition: 'all 0.15s',
                    }}>
                      {DAY_LABELS[d]}
                    </button>
                  ))}
                </div>

                {/* Email editor card */}
                {currentDay && (
                  <div style={cardStyle}>

                    {/* Subject pills */}
                    <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border-light)' }}>
                      <label style={{ ...labelStyle, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        Subject Lines — click to select &amp; use
                      </label>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                        {(currentDay.subject_variants?.length
                          ? currentDay.subject_variants
                          : [currentDay.subject]
                        ).map((s, idx) => (
                          <div key={idx}
                            onClick={() => setChosenSubject(p => ({ ...p, [activeDay]: idx }))}
                            style={{
                              padding: '8px 12px', borderRadius: 7, cursor: 'pointer',
                              background: subjectIdx === idx ? 'rgba(100,116,139,0.08)' : 'var(--bg-elevated)',
                              border: `1px solid ${subjectIdx === idx ? 'var(--color-slate)' : 'transparent'}`,
                              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                              transition: 'all 0.12s',
                            }}>
                            <span style={{
                              fontSize: 13, color: 'var(--text-primary)',
                              fontWeight: subjectIdx === idx ? 600 : 400
                            }}>
                              {idx + 1}. {s}
                            </span>
                            <button
                              onClick={e => { e.stopPropagation(); copy(s, `s${idx}`); }}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 3, flexShrink: 0 }}>
                              {copied === `s${idx}`
                                ? <Check size={12} style={{ color: 'var(--color-emerald)' }} />
                                : <Copy size={12} style={{ color: 'var(--text-muted)' }} />}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Body */}
                    <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border-light)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                        <label style={{ ...labelStyle, margin: 0, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                          Email Body
                        </label>
                        <button
                          onClick={() => handleEnhance(activeDay)}
                          disabled={!!loadingEnhance}
                          style={{
                            padding: '5px 12px', borderRadius: 6, border: '1px solid var(--border-custom)',
                            background: 'var(--bg-elevated)', color: 'var(--color-amber)',
                            fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                            fontWeight: 600, opacity: !!loadingEnhance ? 0.5 : 1,
                          }}>
                          {loadingEnhance === activeDay
                            ? <><Loader2 size={12} className="animate-spin" />Enhancing…</>
                            : <><Sparkles size={12} />Enhance ✨</>}
                        </button>
                      </div>
                      <textarea
                        value={currentBody}
                        onChange={e => setEditedBodies(p => ({ ...p, [activeDay]: e.target.value }))}
                        style={{
                          ...inputStyle, resize: 'vertical', minHeight: 220,
                          lineHeight: 1.75, fontFamily: 'inherit',
                        }}
                      />
                      {currentDay.ps_line && (
                        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6, fontStyle: 'italic' }}>
                          {currentDay.ps_line}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div style={{ padding: '12px 18px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        onClick={() => copy(`Subject: ${currentSubj}\n\n${currentBody}`, 'full')}
                        style={{
                          padding: '8px 16px', borderRadius: 7, border: 'none', cursor: 'pointer',
                          background: 'linear-gradient(135deg, #64748B 0%, #94A3B8 100%)',
                          color: '#fff', fontSize: 13, fontWeight: 600,
                          display: 'flex', alignItems: 'center', gap: 6,
                        }}>
                        {copied === 'full' ? <><Check size={13} />Copied!</> : <><Copy size={13} />Copy Full Email</>}
                      </button>
                      <button
                        onClick={() => setEditedBodies(p => ({ ...p, [activeDay]: sequence?.[activeDay as 'day_0']?.body ?? '' }))}
                        style={{
                          padding: '8px 14px', borderRadius: 7,
                          border: '1px solid var(--border-custom)', background: 'var(--bg-elevated)',
                          color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer',
                          display: 'flex', alignItems: 'center', gap: 6,
                        }}>
                        <RefreshCw size={13} />Reset
                      </button>
                      {activeDay === 'day_0' && (
                        <button onClick={handleMarkSent} style={{
                          padding: '8px 14px', borderRadius: 7,
                          border: '1px solid var(--color-emerald)',
                          background: 'rgba(16,185,129,0.08)', color: 'var(--color-emerald)',
                          fontSize: 13, cursor: 'pointer',
                          display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600,
                        }}>
                          <Send size={13} />Mark as Sent
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* ── Chat strip ───────────────────────────────────────────── */}
                <div style={cardStyle}>
                  <div style={cardHeaderStyle}>
                    <MessageSquare size={14} style={{ color: 'var(--color-slate)' }} />
                    Polish with AI
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
                      "make it shorter" · "add my GitHub" · "be more direct" · "add a P.S."
                    </span>
                  </div>

                  {chatMsgs.length > 0 && (
                    <div style={{ maxHeight: 130, overflowY: 'auto', padding: '10px 16px' }}>
                      {chatMsgs.map((m, i) => (
                        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'flex-start' }}>
                          <span style={{
                            fontSize: 11, fontWeight: 700, flexShrink: 0, marginTop: 1,
                            color: m.role === 'user' ? 'var(--color-blue)' : 'var(--color-emerald)',
                          }}>
                            {m.role === 'user' ? 'You' : 'AI'}
                          </span>
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{m.text}</span>
                        </div>
                      ))}
                      <div ref={chatEndRef} />
                    </div>
                  )}

                  <div style={{ padding: '10px 14px', display: 'flex', gap: 8, borderTop: chatMsgs.length > 0 ? '1px solid var(--border-light)' : 'none' }}>
                    <input
                      value={chatInput}
                      onChange={e => setChatInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && !loadingChat && handleChat()}
                      placeholder={`Refine ${activeDay.replace('_', ' day ')}… (press Enter)`}
                      style={{ ...inputStyle, flex: 1 }}
                    />
                    <button
                      onClick={handleChat}
                      disabled={!chatInput.trim() || loadingChat}
                      style={{
                        padding: '8px 14px', borderRadius: 7, border: 'none', cursor: 'pointer',
                        background: 'var(--color-slate)', color: '#fff', fontSize: 13, fontWeight: 600,
                        opacity: (!chatInput.trim() || loadingChat) ? 0.45 : 1, flexShrink: 0,
                        display: 'flex', alignItems: 'center',
                      }}>
                      {loadingChat ? <Loader2 size={15} className="animate-spin" /> : <ChevronRight size={15} />}
                    </button>
                  </div>
                </div>

                {/* ── Idea box ─────────────────────────────────────────────── */}
                <div style={{
                  ...cardStyle,
                  background: 'linear-gradient(135deg, rgba(245,158,11,0.03) 0%, rgba(16,185,129,0.03) 100%)',
                }}>
                  <div style={cardHeaderStyle}>
                    <Lightbulb size={14} style={{ color: 'var(--color-amber)' }} />
                    Smart Suggestions
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>
                      — model tips to increase reply rate before you hit send
                    </span>
                  </div>
                  <div style={{ padding: '14px 16px' }}>
                    {loadingSuggest ? (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
                        {[0, 1, 2].map(i => (
                          <div key={i} className="skeleton" style={{ height: 70, borderRadius: 8 }} />
                        ))}
                      </div>
                    ) : suggestions.length > 0 ? (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
                        {suggestions.map((s, i) => (
                          <div key={i} style={{
                            padding: '12px 14px', borderRadius: 8,
                            background: 'var(--bg-card)', border: '1px solid var(--border-custom)',
                          }}>
                            <div style={{ fontSize: 22, marginBottom: 6 }}>{s.icon}</div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{s.title}</div>
                            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.55 }}>{s.detail}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
                        Suggestions appear after campaign generation
                      </p>
                    )}
                  </div>
                </div>

              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}