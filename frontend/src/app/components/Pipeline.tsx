// src/app/components/Pipeline.tsx
// All data from /api/leads — no hardcoded rows

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, Search, ChevronDown } from 'lucide-react';

import { BASE_URL } from '../../utils/api';

interface Lead {
  id: number;
  email: string;
  domain: string;
  first_name: string;
  last_name: string;
  position: string;
  status: string;
  purpose: string;
  updated_at: number;
}

const STATUS_OPTIONS = [
  'all', 'discovered', 'verified', 'drafted', 'sent', 'opened', 'replied', 'booked', 'skipped',
];

const STATUS_STYLES: Record<string, { bg: string; color: string; icon: string }> = {
  discovered: { bg: 'rgba(100,116,139,0.08)', color: 'var(--color-slate)', icon: '🔍' },
  verified: { bg: 'rgba(16,185,129,0.08)', color: 'var(--color-emerald)', icon: '✅' },
  drafted: { bg: 'rgba(59,130,246,0.08)', color: 'var(--color-blue)', icon: '📝' },
  sent: { bg: 'rgba(245,158,11,0.08)', color: 'var(--color-amber)', icon: '📤' },
  opened: { bg: 'rgba(124,58,237,0.08)', color: '#7C3AED', icon: '👁' },
  replied: { bg: 'rgba(236,72,153,0.08)', color: 'var(--color-pink)', icon: '💬' },
  booked: { bg: 'rgba(16,185,129,0.12)', color: 'var(--color-emerald)', icon: '📅' },
  skipped: { bg: 'rgba(100,116,139,0.05)', color: 'var(--text-muted)', icon: '⏭' },
};

const PURPOSE_LABELS: Record<string, string> = {
  job_seeker: '💼 Job Seeker',
  startup_founder: '🚀 Startup',
  investor_pitch: '💰 Investor',
  referral_request: '🤝 Referral',
  b2b_sales: '📈 B2B Sales',
  cold_outreach: '📨 Cold',
  partnership: '🔗 Partner',
};

export default function Pipeline() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<number | null>(null);
  const [statusFilter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (search.trim()) params.set('search', search.trim());
      const res = await fetch(`${BASE_URL}/api/leads?${params}`).then(r => r.json());
      setLeads(res.leads ?? []);
      setError(null);
    } catch {
      setError('Cannot reach backend');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search]);

  useEffect(() => { fetchLeads(); }, [fetchLeads]);

  const updateStatus = async (leadId: number, status: string) => {
    setUpdating(leadId);
    try {
      await fetch(`${BASE_URL}/api/leads/${leadId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      });
      setLeads(p => p.map(l => l.id === leadId ? { ...l, status } : l));
      showToast(`Status updated → ${status}`);
    } catch {
      showToast('Update failed');
    } finally {
      setUpdating(null);
    }
  };

  const formatDate = (ts: number) => {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const ss = (s: string) => STATUS_STYLES[s] ?? STATUS_STYLES.discovered;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 32px', minHeight: 'calc(100vh - 56px)', position: 'relative' }}>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 100,
          padding: '10px 18px', borderRadius: 10, fontSize: 13, fontWeight: 600,
          background: 'rgba(16,185,129,0.1)', border: '1px solid var(--color-emerald)',
          color: 'var(--color-emerald)', backdropFilter: 'blur(8px)',
        }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
            Pipeline
          </h2>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>
            {leads.length} lead{leads.length !== 1 ? 's' : ''} — updates when you click Mark as Sent in Outreach
          </p>
        </div>
        <button onClick={fetchLeads} style={{
          background: 'none', border: '1px solid var(--border-custom)', borderRadius: 8,
          padding: '7px 14px', cursor: 'pointer', fontSize: 13,
          color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6,
        }}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        {/* Status pills */}
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', flex: 1 }}>
          {STATUS_OPTIONS.map(s => {
            const active = statusFilter === s;
            const st = s !== 'all' ? ss(s) : null;
            return (
              <button key={s} onClick={() => setFilter(s)} style={{
                padding: '5px 12px', borderRadius: 20, border: 'none', cursor: 'pointer', fontSize: 12,
                fontWeight: active ? 700 : 400,
                background: active ? (st?.bg ?? 'var(--color-slate)') : 'var(--bg-elevated)',
                color: active ? (st?.color ?? '#fff') : 'var(--text-muted)',
                transition: 'all 0.15s',
              }}>
                {s !== 'all' ? `${st?.icon} ` : ''}{s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            );
          })}
        </div>
        {/* Search */}
        <div style={{ position: 'relative' }}>
          <Search size={14} style={{
            position: 'absolute', left: 10, top: '50%',
            transform: 'translateY(-50%)', color: 'var(--text-muted)'
          }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search email or domain…"
            style={{
              padding: '7px 12px 7px 30px', borderRadius: 8, fontSize: 13,
              background: 'var(--bg-elevated)', border: '1px solid var(--border-custom)',
              color: 'var(--text-primary)', width: 220,
            }}
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '12px 16px', borderRadius: 10, marginBottom: 16,
          background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)',
          color: '#EF4444', fontSize: 13
        }}>
          ⚠️ {error}
        </div>
      )}

      {/* Table */}
      <div style={{
        background: 'var(--bg-card)', borderRadius: 12,
        border: '1px solid var(--border-custom)', overflow: 'hidden',
        boxShadow: 'var(--shadow-sm)',
      }}>
        {/* Table header */}
        <div style={{
          display: 'grid', gridTemplateColumns: '2fr 1.5fr 1fr 1fr 1.5fr 1fr',
          padding: '10px 18px', background: 'var(--bg-elevated)',
          borderBottom: '1px solid var(--border-custom)',
        }}>
          {['Contact', 'Company', 'Purpose', 'Status', 'Updated', 'Actions'].map(h => (
            <span key={h} style={{
              fontSize: 11, fontWeight: 700, color: 'var(--text-muted)',
              textTransform: 'uppercase', letterSpacing: '0.06em'
            }}>
              {h}
            </span>
          ))}
        </div>

        {/* Rows */}
        {loading ? (
          [0, 1, 2, 3].map(i => (
            <div key={i} style={{
              display: 'grid', gridTemplateColumns: '2fr 1.5fr 1fr 1fr 1.5fr 1fr',
              padding: '14px 18px', borderBottom: '1px solid var(--border-light)'
            }}>
              {[70, 60, 50, 60, 55, 40].map((w, j) => (
                <div key={j} className="skeleton" style={{ height: 14, width: `${w}%`, borderRadius: 4 }} />
              ))}
            </div>
          ))
        ) : leads.length === 0 ? (
          <div style={{ padding: '48px 20px', textAlign: 'center' }}>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 6 }}>
              No leads yet
            </p>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Find contacts and generate a campaign in the Outreach tab, then click "Mark as Sent"
            </p>
          </div>
        ) : (
          leads.map(lead => {
            const st = ss(lead.status);
            const name = `${lead.first_name} ${lead.last_name}`.trim() || '—';
            return (
              <div key={lead.id} style={{
                display: 'grid', gridTemplateColumns: '2fr 1.5fr 1fr 1fr 1.5fr 1fr',
                padding: '13px 18px', borderBottom: '1px solid var(--border-light)',
                alignItems: 'center', transition: 'background 0.1s',
              }}
                onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-elevated)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>

                {/* Contact */}
                <div style={{ minWidth: 0 }}>
                  <p style={{
                    fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
                    margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                  }}>
                    {name}
                  </p>
                  <p style={{
                    fontSize: 11, color: 'var(--text-muted)', margin: '2px 0 0',
                    fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                  }}>
                    {lead.email}
                  </p>
                </div>

                {/* Company */}
                <span style={{
                  fontSize: 13, color: 'var(--text-secondary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                }}>
                  {lead.domain}
                </span>

                {/* Purpose */}
                <span style={{ fontSize: 11, color: 'var(--color-slate)' }}>
                  {PURPOSE_LABELS[lead.purpose] ?? lead.purpose}
                </span>

                {/* Status badge */}
                <div>
                  <span style={{
                    fontSize: 11, padding: '3px 8px', borderRadius: 10,
                    background: st.bg, color: st.color, fontWeight: 600, whiteSpace: 'nowrap'
                  }}>
                    {st.icon} {lead.status}
                  </span>
                </div>

                {/* Updated */}
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {formatDate(lead.updated_at)}
                </span>

                {/* Actions */}
                <div style={{ position: 'relative' }}>
                  {updating === lead.id ? (
                    <Loader2 size={16} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
                  ) : (
                    <select
                      value={lead.status}
                      onChange={e => updateStatus(lead.id, e.target.value)}
                      style={{
                        padding: '4px 8px', borderRadius: 6, fontSize: 12,
                        background: 'var(--bg-elevated)', border: '1px solid var(--border-custom)',
                        color: 'var(--text-secondary)', cursor: 'pointer',
                      }}>
                      {STATUS_OPTIONS.filter(s => s !== 'all').map(s => (
                        <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {leads.length > 0 && (
        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10, textAlign: 'right' }}>
          Showing {leads.length} leads · Export CSV in Settings
        </p>
      )}
    </div>
  );
}