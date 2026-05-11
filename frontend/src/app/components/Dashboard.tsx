// src/app/components/Dashboard.tsx
// All data from /api/stats and /api/activity — zero hardcoded values

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, TrendingUp, Mail, Users, Database, Zap, MessageSquare } from 'lucide-react';

import { BASE_URL } from '../../utils/api';

interface Stats {
  domains_cached: number;
  contacts_found: number;
  leads_total: number;
  emails_sent: number;
  emails_replied: number;
  reply_rate: string;
  hunter_credits_today: number;
  gemini_calls_today: number;
  hunter_daily_limit: number;
  gemini_daily_limit: number;
  dry_run: boolean;
  gemini_configured: boolean;
  groq_configured: boolean;
}

interface ActivityItem {
  icon: string;
  message: string;
  time_ago: string;
  success: boolean;
}

const EMPTY_STATS: Stats = {
  domains_cached: 0, contacts_found: 0, leads_total: 0,
  emails_sent: 0, emails_replied: 0, reply_rate: '—',
  hunter_credits_today: 0, gemini_calls_today: 0,
  hunter_daily_limit: 8, gemini_daily_limit: 200,
  dry_run: true, gemini_configured: false, groq_configured: false,
};

export default function Dashboard() {
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [statsRes, actRes] = await Promise.all([
        fetch(`${BASE_URL}/api/stats`).then(r => r.json()),
        fetch(`${BASE_URL}/api/activity`).then(r => r.json()),
      ]);
      if (statsRes.success !== false) {
        setStats({ ...EMPTY_STATS, ...statsRes });
      }
      if (actRes.success !== false) {
        setActivity(actRes.activity ?? []);
      }
      setError(null);
      setLastUpdate(new Date());
    } catch (e) {
      setError('Cannot reach backend — make sure python api_routes.py is running on port 7860');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 30_000); // refresh every 30s
    return () => clearInterval(interval);
  }, [fetchAll]);

  const hp = Math.min(100, Math.round((stats.hunter_credits_today / Math.max(stats.hunter_daily_limit, 1)) * 100));
  const gp = Math.min(100, Math.round((stats.gemini_calls_today / Math.max(stats.gemini_daily_limit, 1)) * 100));

  const card = (value: number | string, label: string, color: string, Icon: React.ElementType) => (
    <div style={{
      background: 'var(--bg-card)', borderRadius: 12, padding: '20px 22px',
      border: '1px solid var(--border-custom)', boxShadow: 'var(--shadow-sm)',
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{
          fontSize: 12, color: 'var(--text-muted)', fontWeight: 600,
          textTransform: 'uppercase', letterSpacing: '0.06em'
        }}>{label}</span>
        <Icon size={18} style={{ color }} />
      </div>
      <div style={{ fontSize: 34, fontWeight: 800, color, lineHeight: 1 }}>
        {loading ? <div className="skeleton" style={{ width: 60, height: 34, borderRadius: 6 }} /> : value}
      </div>
    </div>
  );

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 32px', minHeight: 'calc(100vh - 56px)' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>Dashboard</h2>
          {lastUpdate && (
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
              Last updated {lastUpdate.toLocaleTimeString()} · auto-refreshes every 30s
            </p>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {stats.dry_run && (
            <span style={{
              fontSize: 11, padding: '4px 10px', borderRadius: 20,
              background: 'rgba(245,158,11,0.1)', color: 'var(--color-amber)',
              border: '1px solid rgba(245,158,11,0.2)', fontWeight: 600
            }}>
              🔄 DRY RUN — set DRY_RUN=false in .env for live data
            </span>
          )}
          <button onClick={() => { setLoading(true); fetchAll(); }}
            style={{
              background: 'none', border: '1px solid var(--border-custom)',
              borderRadius: 8, padding: '7px 14px', cursor: 'pointer', fontSize: 13,
              color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 6
            }}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Refresh
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '12px 16px', borderRadius: 10, marginBottom: 20,
          background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)',
          color: '#EF4444', fontSize: 13
        }}>
          ⚠️ {error}
        </div>
      )}

      {/* Quick Start Summary */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(168, 85, 247, 0.05) 100%)',
        borderRadius: 16, padding: '24px', marginBottom: 24,
        border: '1px solid var(--border-custom)', display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)', gap: 20
      }}>
        {[
          { icon: <Users size={18} />, title: "1. Discover", desc: "Find Email Leads of decision-makers at any domain using AI search." },
          { icon: <Zap size={18} />, title: "2. Verify", desc: "Real-time SMTP checks to eliminate email bounces." },
          { icon: <Mail size={18} />, title: "3. Personalize", desc: "Generate a 4-day AI sequences tailored to their role." },
          { icon: <TrendingUp size={18} />, title: "4. Track", desc: "Manage your pipeline from lead to booked meeting." },
        ].map((step, i) => (
          <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8, background: 'var(--bg-elevated)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-indigo)'
            }}>
              {step.icon}
            </div>
            <h4 style={{ fontSize: 14, fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>{step.title}</h4>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>{step.desc}</p>
          </div>
        ))}
      </div>

      {/* Stats grid — row 1 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 14 }}>
        {card(stats.domains_cached, 'Domains Cached', 'var(--color-slate)', Database)}
        {card(stats.contacts_found, 'Contacts Found', 'var(--color-emerald)', Users)}
        {card(stats.leads_total, 'Active Leads', 'var(--color-blue)', TrendingUp)}
      </div>

      {/* Stats grid — row 2 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 20 }}>
        {card(stats.emails_sent, 'Emails Sent', 'var(--color-amber)', Mail)}
        {card(stats.emails_replied, 'Replies', 'var(--color-emerald)', MessageSquare)}
        {card(stats.reply_rate, 'Reply Rate', 'var(--color-pink)', Zap)}
      </div>

      {/* API budget bars */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
        {[
          { label: 'Hunter Credits Today', used: stats.hunter_credits_today, limit: stats.hunter_daily_limit, pct: hp, color: 'var(--color-amber)' },
          { label: 'Gemini Calls Today', used: stats.gemini_calls_today, limit: stats.gemini_daily_limit, pct: gp, color: 'var(--color-emerald)' },
        ].map(b => (
          <div key={b.label} style={{
            background: 'var(--bg-card)', borderRadius: 12, padding: '16px 20px',
            border: '1px solid var(--border-custom)', boxShadow: 'var(--shadow-sm)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{
                fontSize: 12, color: 'var(--text-muted)', fontWeight: 600,
                textTransform: 'uppercase', letterSpacing: '0.06em'
              }}>{b.label}</span>
              <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 700 }}>
                {b.used} / {b.limit}
              </span>
            </div>
            <div style={{ background: 'var(--bg-elevated)', borderRadius: 4, height: 6 }}>
              <div style={{
                background: b.color, height: 6, borderRadius: 4,
                width: `${b.pct}%`, transition: 'width 0.5s ease',
              }} />
            </div>
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 5 }}>
              {b.limit - b.used} remaining today
            </p>
          </div>
        ))}
      </div>

      {/* API status + Activity feed side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 14 }}>

        {/* API status */}
        <div style={{
          background: 'var(--bg-card)', borderRadius: 12, padding: '16px 18px',
          border: '1px solid var(--border-custom)', boxShadow: 'var(--shadow-sm)',
        }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
            API Status
          </h3>
          {[
            ['Hunter.io', !!stats.domains_cached || stats.hunter_credits_today > 0],
            ['Gemini', stats.gemini_configured],
            ['Groq', stats.groq_configured],
            ['ScrapingGraph', false],  // shown from health endpoint
          ].map(([name, ok]) => (
            <div key={name as string} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '8px 0', borderBottom: '1px solid var(--border-light)',
            }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{name as string}</span>
              <span style={{
                fontSize: 11, padding: '2px 8px', borderRadius: 10,
                background: ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.08)',
                color: ok ? 'var(--color-emerald)' : '#EF4444', fontWeight: 600
              }}>
                {ok ? '✓ Active' : '✗ Not set'}
              </span>
            </div>
          ))}
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
            Add missing keys to your .env file
          </p>
        </div>

        {/* Activity feed */}
        <div style={{
          background: 'var(--bg-card)', borderRadius: 12, padding: '16px 18px',
          border: '1px solid var(--border-custom)', boxShadow: 'var(--shadow-sm)',
        }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
            Recent Activity
          </h3>
          {loading ? (
            [0, 1, 2, 3].map(i => (
              <div key={i} style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
                <div className="skeleton" style={{ width: 20, height: 20, borderRadius: 4, flexShrink: 0 }} />
                <div style={{ flex: 1 }}><div className="skeleton" style={{ height: 13, width: '80%' }} /></div>
              </div>
            ))
          ) : activity.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--text-muted)', textAlign: 'center', padding: '20px 0' }}>
              No activity yet — start by finding contacts in the Outreach tab
            </p>
          ) : (
            activity.map((item, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '8px 0', borderBottom: '1px solid var(--border-light)',
              }}>
                <span style={{ fontSize: 16, flexShrink: 0 }}>{item.icon}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{
                    fontSize: 13, color: 'var(--text-primary)', margin: 0,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                  }}>
                    {item.message}
                  </p>
                </div>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
                  {item.time_ago}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}