import { Zap } from 'lucide-react';

type Tab = 'dashboard' | 'outreach' | 'pipeline' | 'settings';

interface NavbarProps {
  activeTab: Tab;
  setActiveTab: (tab: Tab) => void;
  mode: 'live' | 'dry_run';
  credits: number;
}

export default function Navbar({ activeTab, setActiveTab, mode, credits }: NavbarProps) {
  const tabs: { id: Tab; label: string }[] = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'outreach', label: 'Outreach' },
    { id: 'pipeline', label: 'Pipeline' },
    { id: 'settings', label: 'Settings' },
  ];

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 glass-effect"
      style={{
        height: '56px',
        borderBottom: '1px solid var(--border-custom)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div className="h-full max-w-[1400px] mx-auto px-6 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <div
              className="flex items-center justify-center w-8 h-8 rounded-lg"
              style={{
                background: 'linear-gradient(135deg, #64748B 0%, #94A3B8 100%)',
              }}
            >
              <Zap className="w-5 h-5 text-white" />
            </div>
            <span
              className="gradient-text"
              style={{ fontSize: '18px', fontWeight: '800', letterSpacing: '-0.02em' }}
            >
              Outreach AI
            </span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className="relative px-6 py-2 rounded-lg transition-all duration-200"
              style={{
                color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                fontWeight: activeTab === tab.id ? '600' : '500',
                background: activeTab === tab.id ? 'var(--bg-card)' : 'transparent',
                boxShadow: activeTab === tab.id ? 'var(--shadow-sm)' : 'none',
              }}
            >
              {tab.label}
              {activeTab === tab.id && (
                <div
                  className="absolute bottom-0 left-1/2 transform -translate-x-1/2 h-0.5 rounded-full transition-all duration-200"
                  style={{
                    width: '60%',
                    background: 'linear-gradient(135deg, #64748B 0%, #94A3B8 100%)',
                  }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Mode Badge & Credits */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-full"
              style={{
                background: mode === 'live' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                border: `1px solid ${mode === 'live' ? 'var(--color-emerald)' : 'var(--color-amber)'}`,
              }}
            >
              <div
                className="w-2 h-2 rounded-full"
                style={{
                  background: mode === 'live' ? 'var(--color-emerald)' : 'var(--color-amber)',
                  boxShadow: `0 0 8px ${mode === 'live' ? 'var(--color-emerald)' : 'var(--color-amber)'}`,
                }}
              />
              <span
                style={{
                  color: mode === 'live' ? 'var(--color-emerald)' : 'var(--color-amber)',
                  fontSize: '13px',
                  fontWeight: '600',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                }}
              >
                {mode === 'live' ? 'LIVE' : 'DRY RUN'}
              </span>
            </div>
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
            {credits} credits left
          </div>
        </div>
      </div>
    </nav>
  );
}
