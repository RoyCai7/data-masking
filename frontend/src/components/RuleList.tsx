import { useState, useEffect, useCallback } from 'react';
import { XMarkIcon, MagnifyingGlassIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { getRulesDetailed, RuleDetail } from '../services/api';

interface RuleListProps {
  onClose: () => void;
}

type ScopeTab = 'public' | 'private';

const CATEGORY_COLORS: Record<string, string> = {
  pii: 'bg-red-100 text-red-700',
  financial: 'bg-yellow-100 text-yellow-700',
  medical: 'bg-blue-100 text-blue-700',
  credential: 'bg-purple-100 text-purple-700',
  network: 'bg-indigo-100 text-indigo-700',
  custom: 'bg-gray-100 text-gray-600',
};

function categoryColor(cat: string) {
  return CATEGORY_COLORS[cat?.toLowerCase()] ?? 'bg-gray-100 text-gray-600';
}

export default function RuleList({ onClose }: RuleListProps) {
  const [rules, setRules] = useState<RuleDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<ScopeTab>('public');
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getRulesDetailed();
      setRules(data.rules || []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load rules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const publicRules = rules.filter(r => r.scope === 'system' || r.scope === 'org');
  const privateRules = rules.filter(r => r.scope === 'private');

  const filtered = (tab === 'public' ? publicRules : privateRules).filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return r.id.toLowerCase().includes(q) || r.name.toLowerCase().includes(q) || r.category?.toLowerCase().includes(q);
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Masking Rules</h2>
            <p className="text-xs text-gray-500 mt-0.5">Rules available in your current context</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              className="p-2 rounded-lg text-gray-400 hover:text-suse-green hover:bg-gray-100 transition-colors"
              title="Refresh"
            >
              <ArrowPathIcon className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            >
              <XMarkIcon className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tabs + Search */}
        <div className="px-6 pt-4 pb-3 space-y-3 border-b border-gray-100">
          <div className="flex gap-1 p-1 bg-gray-100 rounded-xl">
            <button
              onClick={() => { setTab('public'); setSearch(''); }}
              className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === 'public' ? 'bg-white shadow text-suse-green' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              🌐 Public
              <span className="ml-1.5 text-xs px-1.5 py-0.5 rounded-full bg-gray-200 text-gray-600">
                {publicRules.length}
              </span>
            </button>
            <button
              onClick={() => { setTab('private'); setSearch(''); }}
              className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === 'private' ? 'bg-white shadow text-suse-green' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              🔒 Private
              <span className="ml-1.5 text-xs px-1.5 py-0.5 rounded-full bg-gray-200 text-gray-600">
                {privateRules.length}
              </span>
            </button>
          </div>

          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search by id, name or category…"
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-suse-green/30"
            />
          </div>
        </div>

        {/* Rule list */}
        <div className="flex-1 overflow-y-auto px-6 py-3 space-y-2">
          {loading && (
            <div className="text-center py-12 text-gray-400 text-sm">Loading…</div>
          )}
          {!loading && error && (
            <div className="text-center py-12 text-red-500 text-sm">{error}</div>
          )}
          {!loading && !error && filtered.length === 0 && (
            <div className="text-center py-12 text-gray-400 text-sm">
              {search ? 'No rules match your search.' : tab === 'private' ? 'No private rules yet. Use "New Rule" to create one.' : 'No public rules found.'}
            </div>
          )}
          {!loading && filtered.map(rule => (
            <div
              key={rule.id}
              className={`flex items-start gap-3 p-3.5 rounded-xl border transition-colors ${
                rule.enabled === false ? 'bg-gray-50 border-gray-200 opacity-60' : 'bg-white border-gray-200 hover:border-suse-green/40 hover:bg-green-50/30'
              }`}
            >
              {/* Scope badge */}
              <span className="mt-0.5 text-lg leading-none shrink-0" title={`scope: ${rule.scope}`}>
                {rule.scope === 'system' ? '🌐' : rule.scope === 'org' ? '🏢' : '🔒'}
              </span>

              <div className="flex-1 min-w-0">
                <div className="flex items-center flex-wrap gap-1.5">
                  <span className="font-semibold text-sm text-gray-900 truncate">{rule.name}</span>
                  {rule.enabled === false && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 text-gray-500">disabled</span>
                  )}
                  {(rule.use_count ?? 0) > 0 && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-orange-100 text-orange-600">🔥 {rule.use_count}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <code className="text-xs text-gray-400">{rule.id}</code>
                  {rule.category && (
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${categoryColor(rule.category)}`}>
                      {rule.category}
                    </span>
                  )}
                </div>
                {rule.pattern && (
                  <p className="mt-1.5 text-xs text-gray-500 font-mono bg-gray-50 rounded px-2 py-1 truncate" title={rule.pattern}>
                    {rule.description
                      ? <><span className="not-italic text-gray-600">{rule.description}</span></>                      : rule.pattern}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-100 flex justify-between items-center text-xs text-gray-400">
          <span>
            {tab === 'public'
              ? `${filtered.length} of ${publicRules.length} public rules`
              : `${filtered.length} of ${privateRules.length} private rules`}
          </span>
          <span>🌐 system · 🏢 org · 🔒 private</span>
        </div>
      </div>
    </div>
  );
}
