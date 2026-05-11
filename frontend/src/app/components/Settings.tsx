import { useState } from 'react';
import { CheckCircle, XCircle, Download, Trash2, User, Building, Linkedin } from 'lucide-react';

interface APIStatus {
  name: string;
  configured: boolean;
  description: string;
  icon: string;
}

export default function Settings() {
  const [hunterLimit, setHunterLimit] = useState(500);
  const [geminiLimit, setGeminiLimit] = useState(1500);

  const [profile, setProfile] = useState({
    name: '',
    title: '',
    company: '',
    linkedin: '',
    background: '',
  });

  const apiStatuses: APIStatus[] = [
    {
      name: 'Hunter.io',
      configured: true,
      description: 'Email finder & verification',
      icon: '🎯',
    },
    {
      name: 'Google Gemini',
      configured: true,
      description: 'AI email generation',
      icon: '✨',
    },
    {
      name: 'Groq',
      configured: false,
      description: 'Alternative AI model (fast)',
      icon: '⚡',
    },
    {
      name: 'ScrapingGraph',
      configured: false,
      description: 'Web scraping fallback',
      icon: '🕷️',
    },
  ];

  const handleSaveProfile = () => {
    localStorage.setItem('outreach_profile', JSON.stringify(profile));
    // Show success toast
  };

  const handleExportCSV = () => {
    // Trigger CSV export
  };

  const handleClearDatabase = () => {
    if (confirm('Are you sure? This will delete all leads and cannot be undone.')) {
      // Clear database
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-8 py-8">
      <div className="grid grid-cols-2 gap-8">
        {/* Left Column - API Configuration */}
        <div>
          <h2 className="mb-6" style={{ color: 'var(--text-primary)', fontSize: '20px', fontWeight: '700' }}>
            API Configuration
          </h2>
          <div className="space-y-4">
            {apiStatuses.map((api) => (
              <div
                key={api.name}
                className="p-5 rounded-xl transition-all duration-200 hover:scale-[1.01]"
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-custom)',
                  boxShadow: 'var(--shadow-md)',
                }}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <span style={{ fontSize: '24px' }}>{api.icon}</span>
                    <div>
                      <div style={{ color: 'var(--text-primary)', fontSize: '16px', fontWeight: '600' }}>
                        {api.name}
                      </div>
                      <div style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                        {api.description}
                      </div>
                    </div>
                  </div>
                  {api.configured ? (
                    <div className="flex items-center gap-2">
                      <CheckCircle size={20} style={{ color: 'var(--color-emerald)' }} />
                      <span
                        className="px-3 py-1 rounded-full"
                        style={{
                          background: 'rgba(16, 185, 129, 0.1)',
                          color: 'var(--color-emerald)',
                          fontSize: '12px',
                          fontWeight: '600',
                        }}
                      >
                        Configured
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <XCircle size={20} style={{ color: 'var(--text-muted)' }} />
                      <span
                        className="px-3 py-1 rounded-full"
                        style={{
                          background: 'rgba(148, 163, 184, 0.1)',
                          color: 'var(--text-muted)',
                          fontSize: '12px',
                          fontWeight: '600',
                        }}
                      >
                        Not Set
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Usage Limits */}
          <h2 className="mt-8 mb-6" style={{ color: 'var(--text-primary)', fontSize: '20px', fontWeight: '700' }}>
            Daily Limits
          </h2>
          <div className="space-y-4">
            <div
              className="p-5 rounded-xl"
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-custom)',
                boxShadow: 'var(--shadow-md)',
              }}
            >
              <label
                className="block mb-3"
                style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600' }}
              >
                Hunter.io Daily Limit
              </label>
              <input
                type="number"
                value={hunterLimit}
                onChange={(e) => setHunterLimit(Number(e.target.value))}
                className="w-full px-4 py-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2"
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-custom)',
                  color: 'var(--text-primary)',
                  fontSize: '15px',
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = 'var(--color-slate)';
                  e.target.style.boxShadow = '0 0 0 3px rgba(100, 116, 139, 0.1)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = 'var(--border-custom)';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>
            <div
              className="p-5 rounded-xl"
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-custom)',
                boxShadow: 'var(--shadow-md)',
              }}
            >
              <label
                className="block mb-3"
                style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600' }}
              >
                Gemini Daily Limit
              </label>
              <input
                type="number"
                value={geminiLimit}
                onChange={(e) => setGeminiLimit(Number(e.target.value))}
                className="w-full px-4 py-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2"
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-custom)',
                  color: 'var(--text-primary)',
                  fontSize: '15px',
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = 'var(--color-slate)';
                  e.target.style.boxShadow = '0 0 0 3px rgba(100, 116, 139, 0.1)';
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = 'var(--border-custom)';
                  e.target.style.boxShadow = 'none';
                }}
              />
            </div>
          </div>
        </div>

        {/* Right Column - Sender Profile */}
        <div>
          <h2 className="mb-6" style={{ color: 'var(--text-primary)', fontSize: '20px', fontWeight: '700' }}>
            Sender Profile
          </h2>
          <div
            className="p-6 rounded-xl mb-6"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-custom)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <div className="space-y-4">
              <div>
                <label
                  className="flex items-center gap-2 mb-2"
                  style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600' }}
                >
                  <User size={16} />
                  Your Name
                </label>
                <input
                  type="text"
                  value={profile.name}
                  onChange={(e) => setProfile({ ...profile, name: e.target.value })}
                  placeholder="John Doe"
                  className="w-full px-4 py-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2"
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-custom)',
                    color: 'var(--text-primary)',
                    fontSize: '15px',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'var(--color-slate)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(100, 116, 139, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'var(--border-custom)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>
              <div>
                <label
                  className="flex items-center gap-2 mb-2"
                  style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600' }}
                >
                  <User size={16} />
                  Your Title
                </label>
                <input
                  type="text"
                  value={profile.title}
                  onChange={(e) => setProfile({ ...profile, title: e.target.value })}
                  placeholder="Software Engineer"
                  className="w-full px-4 py-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2"
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-custom)',
                    color: 'var(--text-primary)',
                    fontSize: '15px',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'var(--color-slate)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(100, 116, 139, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'var(--border-custom)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>
              <div>
                <label
                  className="flex items-center gap-2 mb-2"
                  style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600' }}
                >
                  <Building size={16} />
                  Your Company
                </label>
                <input
                  type="text"
                  value={profile.company}
                  onChange={(e) => setProfile({ ...profile, company: e.target.value })}
                  placeholder="Acme Corp"
                  className="w-full px-4 py-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2"
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-custom)',
                    color: 'var(--text-primary)',
                    fontSize: '15px',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'var(--color-slate)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(100, 116, 139, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'var(--border-custom)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>
              <div>
                <label
                  className="flex items-center gap-2 mb-2"
                  style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600' }}
                >
                  <Linkedin size={16} />
                  LinkedIn URL
                </label>
                <input
                  type="text"
                  value={profile.linkedin}
                  onChange={(e) => setProfile({ ...profile, linkedin: e.target.value })}
                  placeholder="https://linkedin.com/in/yourprofile"
                  className="w-full px-4 py-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2"
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-custom)',
                    color: 'var(--text-primary)',
                    fontSize: '15px',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'var(--color-slate)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(100, 116, 139, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'var(--border-custom)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>
              <div>
                <label
                  className="block mb-2"
                  style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600' }}
                >
                  Background / Key Skills
                </label>
                <textarea
                  value={profile.background}
                  onChange={(e) => setProfile({ ...profile, background: e.target.value })}
                  placeholder="Brief background or key achievements..."
                  rows={4}
                  className="w-full px-4 py-3 rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 resize-none"
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-custom)',
                    color: 'var(--text-primary)',
                    fontSize: '15px',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'var(--color-slate)';
                    e.target.style.boxShadow = '0 0 0 3px rgba(100, 116, 139, 0.1)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'var(--border-custom)';
                    e.target.style.boxShadow = 'none';
                  }}
                />
              </div>
            </div>
            <button
              onClick={handleSaveProfile}
              className="w-full mt-4 py-3 rounded-lg transition-all duration-300 hover:scale-[1.02] active:scale-[0.98]"
              style={{
                background: 'linear-gradient(135deg, #64748B 0%, #94A3B8 100%)',
                color: 'white',
                fontSize: '15px',
                fontWeight: '700',
                boxShadow: 'var(--shadow-md)',
              }}
            >
              Save Profile
            </button>
          </div>

          {/* Danger Zone */}
          <div
            className="p-6 rounded-xl"
            style={{
              background: 'var(--bg-card)',
              border: '2px solid rgba(239, 68, 68, 0.2)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <h3 className="mb-4" style={{ color: '#EF4444', fontSize: '16px', fontWeight: '700' }}>
              Danger Zone
            </h3>
            <div className="space-y-3">
              <button
                onClick={handleExportCSV}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg transition-all duration-200 hover:bg-opacity-80"
                style={{
                  background: 'var(--bg-elevated)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-custom)',
                  fontSize: '14px',
                  fontWeight: '600',
                }}
              >
                <Download size={18} />
                Export Leads CSV
              </button>
              <button
                onClick={handleClearDatabase}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg transition-all duration-200 hover:bg-opacity-90"
                style={{
                  background: 'rgba(239, 68, 68, 0.1)',
                  color: '#EF4444',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  fontSize: '14px',
                  fontWeight: '600',
                }}
              >
                <Trash2 size={18} />
                Clear Database
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
