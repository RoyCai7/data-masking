import { useState, useEffect, useCallback } from 'react';
import { KeyIcon, LightBulbIcon, ShieldCheckIcon } from '@heroicons/react/24/outline';
import { getApiKey, getMyKeyInfo, getSystemStatus, KeyInfo, SystemStatus } from '../services/api';
import AdminConsole from './AdminConsole';
import Settings from './Settings';
import SuggestRule from './SuggestRule';
import RuleList from './RuleList';
import MyOrg from './MyOrg';

// SUSE Chameleon Logo SVG
const SuseLogo = () => (
  <svg className="h-8 w-8" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="50" cy="50" r="45" fill="#0C322C"/>
    <path d="M30 50 Q50 30 70 50 Q50 70 30 50" fill="#30BA78"/>
    <circle cx="50" cy="50" r="8" fill="#7FE0B5"/>
  </svg>
);

export default function Header() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [keyInfo, setKeyInfo] = useState<KeyInfo | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showAdminConsole, setShowAdminConsole] = useState(false);
  const [showSuggestRule, setShowSuggestRule] = useState(false);
  const [showRuleList, setShowRuleList] = useState(false);
  const [showMyOrg, setShowMyOrg] = useState(false);

  const refreshKeyInfo = useCallback(async () => {
    if (!getApiKey()) {
      setKeyInfo(null);
      return;
    }

    try {
      const info = await getMyKeyInfo();
      setKeyInfo(info);
    } catch {
      setKeyInfo(null);
    }
  }, []);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await getSystemStatus();
        setStatus(data);
      } catch (error) {
        console.error('Failed to fetch status:', error);
      }
    };

    fetchStatus();
    refreshKeyInfo();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [refreshKeyInfo]);

  // Listen for 401 auth errors to auto-open Settings
  useEffect(() => {
    const handler = () => setShowSettings(true);
    window.addEventListener('api-key-required', handler);
    return () => window.removeEventListener('api-key-required', handler);
  }, []);

  useEffect(() => {
    const handler = () => refreshKeyInfo();
    window.addEventListener('auth-state-changed', handler);
    return () => window.removeEventListener('auth-state-changed', handler);
  }, [refreshKeyInfo]);

  const isAdmin = keyInfo?.role === 'admin';

  return (
    <header className="bg-suse-green-dark text-white shadow-lg">
      <div className="max-w-6xl mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo and Title */}
          <div className="flex items-center space-x-3">
            <SuseLogo />
            <div>
              <h1 className="text-xl font-bold">Data Masking Service</h1>
              <p className="text-xs text-suse-green-light">Sensitive Data Protection</p>
            </div>
          </div>

          {/* Status Badge */}
          <div className="flex items-center space-x-4">
            {status && (
              <div className="flex items-center space-x-2 bg-suse-green-dark/50 rounded-full px-4 py-1.5">
                <span className={`w-2 h-2 rounded-full ${
                  status.executor.available_slots > 0 ? 'bg-suse-green animate-pulse' : 'bg-yellow-400'
                }`} />
                <span className="text-sm">
                  {status.executor.active_tasks}/{status.executor.max_workers} tasks
                </span>
              </div>
            )}
            
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-suse-green-light hover:text-white transition-colors"
            >
              API Docs
            </a>

            <button
              onClick={() => setShowRuleList(true)}
              className="flex items-center space-x-1 text-sm text-suse-green-light hover:text-white transition-colors"
              title="Browse Rules"
            >
              <span className="text-base leading-none">📋</span>
              <span>Rules</span>
            </button>

            {keyInfo && (
              <button
                onClick={() => setShowMyOrg(true)}
                className="flex items-center space-x-1 text-sm text-suse-green-light hover:text-white transition-colors"
                title="My Organization"
              >
                <span className="text-base leading-none">🏢</span>
                <span>My Org</span>
              </button>
            )}

            <button
              onClick={() => setShowSuggestRule(true)}
              className="flex items-center space-x-1 text-sm text-amber-200 hover:text-white transition-colors"
              title="New Rule"
            >
              <LightBulbIcon className="w-4 h-4" />
              <span>New Rule</span>
            </button>

            <button
              onClick={() => setShowSettings(true)}
              className="flex items-center space-x-1 text-sm text-suse-green-light hover:text-white transition-colors"
              title="API Key Settings"
            >
              <KeyIcon className="w-4 h-4" />
              <span>Key</span>
            </button>

            {isAdmin && (
              <button
                onClick={() => setShowAdminConsole(true)}
                className="flex items-center space-x-1 text-sm text-amber-200 hover:text-white transition-colors"
                title="Admin Console"
              >
                <ShieldCheckIcon className="w-4 h-4" />
                <span>Admin</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {showSettings && <Settings onClose={() => setShowSettings(false)} />}
      {showAdminConsole && <AdminConsole onClose={() => setShowAdminConsole(false)} />}
      {showSuggestRule && <SuggestRule onClose={() => setShowSuggestRule(false)} />}
      {showRuleList && <RuleList onClose={() => setShowRuleList(false)} />}
      {showMyOrg && <MyOrg onClose={() => setShowMyOrg(false)} />}
    </header>
  );
}
