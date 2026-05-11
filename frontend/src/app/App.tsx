import { useState } from 'react';
import Navbar from './components/Navbar';
import Dashboard from './components/Dashboard';
import Outreach from './components/Outreach';
import Pipeline from './components/Pipeline';
import Settings from './components/Settings';

type Tab = 'dashboard' | 'outreach' | 'pipeline' | 'settings';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [mode, setMode] = useState<'live' | 'dry_run'>('dry_run');
  const [credits, setCredits] = useState(8);

  const renderTabContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />;
      case 'outreach':
        return <Outreach />;
      case 'pipeline':
        return <Pipeline />;
      case 'settings':
        return <Settings />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        mode={mode}
        credits={credits}
      />
      <main className="pt-[56px]">
        <div className="animate-fadeIn">
          {renderTabContent()}
        </div>
      </main>
    </div>
  );
}
