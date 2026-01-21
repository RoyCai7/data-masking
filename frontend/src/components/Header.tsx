import { useState, useEffect } from 'react';
import { getSystemStatus, SystemStatus } from '../services/api';

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
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

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
          </div>
        </div>
      </div>
    </header>
  );
}
