import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type MouseEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ClipboardIcon,
  DocumentArrowUpIcon,
  KeyIcon,
  ShieldCheckIcon,
  SparklesIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import {
  RuleChangelogEntry,
  RuleDetail,
  RuleSuggestion,
  ManagedKeyInfo,
  createApiKey,
  createRule,
  deleteRule,
  disableApiKey,
  exportRules,
  importRules,
  listApiKeys,
  listRuleChangelog,
  listRuleSuggestions,
  getMyKeyInfo,
  getRulesDetailed,
  reviewRuleSuggestion,
  toggleRule,
  updateRule,
} from '../services/api';
import { useModalA11y } from '../hooks/useModalA11y';

type AdminTab = 'keys' | 'rules' | 'suggestions' | 'history';

interface AdminConsoleProps {
  onClose: () => void;
}

const emptyRule: RuleDetail = {
  id: '',
  name: '',
  category: 'custom',
  pattern: '',
  flags: '',
  strategy: 'placeholder',
  placeholder: '[MASKED]',
  weight: 5,
  enabled: true,
};

const tabs: Array<{ id: AdminTab; label: string }> = [
  { id: 'keys', label: 'Keys' },
  { id: 'rules', label: 'Rules' },
  { id: 'suggestions', label: 'Rule Approvals' },
  { id: 'history', label: 'History' },
];

export default function AdminConsole({ onClose }: AdminConsoleProps) {
  const dialogRef = useModalA11y(onClose);
  const [activeTab, setActiveTab] = useState<AdminTab>('keys');
  const [isReady, setIsReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [keys, setKeys] = useState<ManagedKeyInfo[]>([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyRole, setNewKeyRole] = useState<'admin' | 'user'>('user');
  const [newKeyExpiry, setNewKeyExpiry] = useState(365);
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  const [rules, setRules] = useState<RuleDetail[]>([]);
  const [ruleFilter, setRuleFilter] = useState('');
  const [ruleForm, setRuleForm] = useState<RuleDetail>(emptyRule);
  const [isEditingRule, setIsEditingRule] = useState(false);
  const [importText, setImportText] = useState('');

  const [suggestionStatus, setSuggestionStatus] = useState<'pending' | 'approved' | 'rejected' | 'all'>('pending');
  const [suggestions, setSuggestions] = useState<RuleSuggestion[]>([]);

  const [historyRuleId, setHistoryRuleId] = useState('');
  const [historyEntries, setHistoryEntries] = useState<RuleChangelogEntry[]>([]);

  const showMessage = (message: string) => {
    setSuccess(message);
    window.setTimeout(() => setSuccess(null), 3000);
  };

  const handleError = (err: any, fallback: string) => {
    setError(err?.response?.data?.detail || err?.message || fallback);
  };

  const loadKeys = useCallback(async () => {
    const response = await listApiKeys();
    setKeys(response.keys || []);
  }, []);

  const loadRules = useCallback(async () => {
    const response = await getRulesDetailed();
    setRules(response.rules || []);
  }, []);

  const loadSuggestions = useCallback(async () => {
    const response = await listRuleSuggestions(suggestionStatus === 'all' ? undefined : suggestionStatus);
    setSuggestions(response.suggestions || []);
  }, [suggestionStatus]);

  const loadHistory = useCallback(async () => {
    const response = await listRuleChangelog({ rule_id: historyRuleId || undefined, limit: 100 });
    setHistoryEntries(response.changelog || []);
  }, [historyRuleId]);

  const refreshActiveTab = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      if (activeTab === 'keys') {
        await loadKeys();
      } else if (activeTab === 'rules') {
        await loadRules();
      } else if (activeTab === 'suggestions') {
        await loadSuggestions();
      } else {
        await loadHistory();
      }
    } catch (err) {
      handleError(err, 'Failed to load admin data');
    } finally {
      setLoading(false);
    }
  }, [activeTab, loadHistory, loadKeys, loadRules, loadSuggestions]);

  useEffect(() => {
    const bootstrap = async () => {
      setLoading(true);
      try {
        const keyInfo = await getMyKeyInfo();
        if (keyInfo.role !== 'admin') {
          throw new Error('Admin role required');
        }
        setIsReady(true);
        await loadKeys();
      } catch (err) {
        handleError(err, 'Admin role required');
      } finally {
        setLoading(false);
      }
    };

    bootstrap();
  }, [loadKeys]);

  useEffect(() => {
    if (!isReady) return;
    refreshActiveTab();
  }, [activeTab, isReady, refreshActiveTab]);

  useEffect(() => {
    if (!isReady || activeTab !== 'suggestions') return;
    refreshActiveTab();
  }, [suggestionStatus, isReady, activeTab, refreshActiveTab]);

  const filteredRules = useMemo(() => {
    const keyword = ruleFilter.trim().toLowerCase();
    if (!keyword) return rules;
    return rules.filter((rule: RuleDetail) =>
      [rule.id, rule.name, rule.category, rule.pattern].some((value) =>
        value?.toLowerCase().includes(keyword)
      )
    );
  }, [ruleFilter, rules]);

  const resetRuleForm = () => {
    setRuleForm(emptyRule);
    setIsEditingRule(false);
  };

  const handleCreateKey = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await createApiKey({
        name: newKeyName.trim(),
        role: newKeyRole,
        expires_days: newKeyExpiry,
      });
      setCreatedKey(result.key);
      setNewKeyName('');
      setNewKeyRole('user');
      setNewKeyExpiry(365);
      await loadKeys();
      showMessage('API key created');
    } catch (err) {
      handleError(err, 'Failed to create API key');
    } finally {
      setLoading(false);
    }
  };

  const handleDisableKey = async (keyPreview: string) => {
    const target = window.prompt(`Paste the full key to disable this entry (${keyPreview})`);
    if (!target) return;

    setLoading(true);
    setError(null);
    try {
      await disableApiKey(target.trim());
      await loadKeys();
      showMessage('API key disabled');
    } catch (err) {
      handleError(err, 'Failed to disable API key');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveRule = async () => {
    setLoading(true);
    setError(null);
    try {
      if (isEditingRule) {
        const { id, is_builtin, version, created_at, updated_at, created_by, ...payload } = ruleForm;
        await updateRule(id, payload);
        showMessage(`Rule '${id}' updated`);
      } else {
        const { is_builtin, version, created_at, updated_at, created_by, ...payload } = ruleForm;
        await createRule(payload);
        showMessage(`Rule '${ruleForm.id}' created`);
      }
      await loadRules();
      resetRuleForm();
    } catch (err) {
      handleError(err, 'Failed to save rule');
    } finally {
      setLoading(false);
    }
  };

  const handleEditRule = (rule: RuleDetail) => {
    setRuleForm(rule);
    setIsEditingRule(true);
    setActiveTab('rules');
    setError(null);
  };

  const handleToggleRule = async (ruleId: string) => {
    setLoading(true);
    setError(null);
    try {
      await toggleRule(ruleId);
      await loadRules();
      showMessage(`Rule '${ruleId}' toggled`);
    } catch (err) {
      handleError(err, 'Failed to toggle rule');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    if (!window.confirm(`Delete rule '${ruleId}'? This only works for custom rules.`)) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await deleteRule(ruleId);
      await loadRules();
      if (ruleForm.id === ruleId) {
        resetRuleForm();
      }
      showMessage(`Rule '${ruleId}' deleted`);
    } catch (err) {
      handleError(err, 'Failed to delete rule');
    } finally {
      setLoading(false);
    }
  };

  const handleExportRules = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await exportRules();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'rules-export.json';
      link.click();
      URL.revokeObjectURL(url);
      showMessage('Rules exported');
    } catch (err) {
      handleError(err, 'Failed to export rules');
    } finally {
      setLoading(false);
    }
  };

  const handleImportRules = async () => {
    setLoading(true);
    setError(null);
    try {
      const parsed = JSON.parse(importText);
      const rulesPayload = Array.isArray(parsed) ? parsed : parsed.rules;
      if (!Array.isArray(rulesPayload)) {
        throw new Error('Expected a JSON array or an object with a rules array');
      }
      const result = await importRules(rulesPayload);
      await loadRules();
      showMessage(`Import complete: ${result.created} created, ${result.updated} updated`);
      setImportText('');
    } catch (err) {
      handleError(err, 'Failed to import rules');
    } finally {
      setLoading(false);
    }
  };

  const handleReviewSuggestion = async (suggestionId: number, action: 'approve' | 'reject') => {
    setLoading(true);
    setError(null);
    try {
      await reviewRuleSuggestion(suggestionId, action);
      await loadSuggestions();
      if (action === 'approve') {
        await loadRules();
      }
      showMessage(`Suggestion ${action}d`);
    } catch (err) {
      handleError(err, `Failed to ${action} suggestion`);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
    showMessage('Copied to clipboard');
  };

  const prettyJson = (value?: string | null) => {
    if (!value) return '—';
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Admin Console"
        tabIndex={-1}
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.96, opacity: 0 }}
        onClick={(e: MouseEvent<HTMLDivElement>) => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-xl w-full max-w-7xl h-[90vh] overflow-hidden flex flex-col outline-none"
      >
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-suse-green-50 rounded-lg">
              <ShieldCheckIcon className="w-6 h-6 text-suse-green" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">Admin Console</h2>
              <p className="text-sm text-gray-500">Manage keys, rules, suggestions, and audit history</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-gray-100 transition-colors">
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <div className="px-6 pt-4 flex items-center justify-between gap-4 border-b border-gray-100">
          <div className="flex gap-2 overflow-x-auto pb-4">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'bg-suse-green text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <button
            onClick={refreshActiveTab}
            className="pb-4 text-sm text-suse-green font-medium hover:text-suse-green-dark transition-colors"
          >
            Refresh
          </button>
        </div>

        <div className="px-6 py-3 space-y-3">
          <AnimatePresence>
            {error && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="p-3 rounded-lg bg-red-50 text-red-700 text-sm border border-red-200">
                {error}
              </motion.div>
            )}
          </AnimatePresence>
          <AnimatePresence>
            {success && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="p-3 rounded-lg bg-green-50 text-green-700 text-sm border border-green-200 flex items-center gap-2">
                <CheckCircleIcon className="w-4 h-4" />
                <span>{success}</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="flex-1 overflow-auto px-6 pb-6">
          {!isReady ? (
            <div className="h-full flex items-center justify-center text-gray-500">
              {loading ? 'Loading admin console…' : 'Admin role required'}
            </div>
          ) : activeTab === 'keys' ? (
            <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] gap-6">
              <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-4">
                <div className="flex items-center gap-2">
                  <KeyIcon className="w-5 h-5 text-suse-green" />
                  <h3 className="font-semibold text-gray-900">Create API Key</h3>
                </div>
                <input value={newKeyName} onChange={(e: ChangeEvent<HTMLInputElement>) => setNewKeyName(e.target.value)} placeholder="Owner name" className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                <div className="grid grid-cols-2 gap-3">
                  <select value={newKeyRole} onChange={(e: ChangeEvent<HTMLSelectElement>) => setNewKeyRole(e.target.value as 'admin' | 'user')} className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white">
                    <option value="user">user</option>
                    <option value="admin">admin</option>
                  </select>
                  <input type="number" min={1} value={newKeyExpiry} onChange={(e: ChangeEvent<HTMLInputElement>) => setNewKeyExpiry(Number(e.target.value) || 365)} className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                </div>
                <button onClick={handleCreateKey} disabled={loading || !newKeyName.trim()} className="w-full px-4 py-2.5 rounded-lg bg-suse-green text-white font-medium disabled:opacity-50">
                  {loading ? 'Working…' : 'Create Key'}
                </button>
                {createdKey && (
                  <div className="p-4 bg-green-50 border border-green-200 rounded-xl space-y-2">
                    <p className="text-sm font-medium text-green-800">New key created</p>
                    <code className="block text-xs bg-white border rounded p-3 break-all text-gray-800">{createdKey}</code>
                    <button onClick={() => copyToClipboard(createdKey)} className="inline-flex items-center gap-2 text-sm text-green-700 font-medium">
                      <ClipboardIcon className="w-4 h-4" /> Copy
                    </button>
                  </div>
                )}
              </div>
              <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between">
                  <h3 className="font-semibold text-gray-900">Existing Keys</h3>
                  <span className="text-sm text-gray-500">{keys.filter(k => k.enabled).length} total</span>
                </div>
                <div className="divide-y divide-gray-100">
                  {keys.filter(k => k.enabled).map((key) => (
                    <div key={`${key.name}-${key.key || key.key_preview}`} className="px-5 py-4 flex items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900">{key.name}</span>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${key.role === 'admin' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-700'}`}>{key.role}</span>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${key.enabled ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{key.enabled ? 'enabled' : 'disabled'}</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1 font-mono">{key.key || key.key_preview}</p>
                        <p className="text-xs text-gray-400 mt-1">Created {key.created_at} · Expires {key.expires_at}</p>
                      </div>
                      {key.enabled && (
                        <button onClick={() => handleDisableKey(key.key || key.key_preview)} className="px-3 py-2 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 text-sm">
                          Disable
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : activeTab === 'rules' ? (
            <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-6">
              <div className="space-y-6">
                <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-gray-900">{isEditingRule ? `Edit Rule: ${ruleForm.id}` : 'Create Rule'}</h3>
                    {isEditingRule && (
                      <button onClick={resetRuleForm} className="text-sm text-gray-500 hover:text-gray-700">New Rule</button>
                    )}
                  </div>
                  <input disabled={isEditingRule} value={ruleForm.id} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, id: e.target.value }))} placeholder="rule_id" className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 disabled:bg-gray-50" />
                  <input value={ruleForm.name} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, name: e.target.value }))} placeholder="Rule name" className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                  <div className="grid grid-cols-2 gap-3">
                    <input value={ruleForm.category} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, category: e.target.value }))} placeholder="category" className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                    <select value={ruleForm.strategy} onChange={(e: ChangeEvent<HTMLSelectElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, strategy: e.target.value as RuleDetail['strategy'] }))} className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white">
                      <option value="placeholder">placeholder</option>
                      <option value="partial">partial</option>
                      <option value="asterisk">asterisk</option>
                      <option value="hash">hash</option>
                    </select>
                  </div>
                  <input value={ruleForm.flags} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, flags: e.target.value }))} placeholder="Regex flags, e.g. IGNORECASE" className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                  <input value={ruleForm.placeholder} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, placeholder: e.target.value }))} placeholder="Replacement text" className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                  <textarea value={ruleForm.pattern} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, pattern: e.target.value }))} placeholder="Regex pattern" rows={5} className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 font-mono" />
                  <div className="grid grid-cols-2 gap-3">
                    <input type="number" min={0} max={100} value={ruleForm.weight} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, weight: Number(e.target.value) || 0 }))} className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                    <label className="flex items-center gap-2 px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-700">
                      <input type="checkbox" checked={ruleForm.enabled} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleForm((prev: RuleDetail) => ({ ...prev, enabled: e.target.checked }))} />
                      Enabled
                    </label>
                  </div>
                  <button onClick={handleSaveRule} disabled={loading || !ruleForm.id || !ruleForm.name || !ruleForm.pattern} className="w-full px-4 py-2.5 rounded-lg bg-suse-green text-white font-medium disabled:opacity-50">
                    {loading ? 'Working…' : isEditingRule ? 'Update Rule' : 'Create Rule'}
                  </button>
                </div>
                <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-gray-900">Import / Export</h3>
                    <button onClick={handleExportRules} className="inline-flex items-center gap-2 text-sm text-suse-green font-medium">
                      <ArrowDownTrayIcon className="w-4 h-4" /> Export
                    </button>
                  </div>
                  <textarea value={importText} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setImportText(e.target.value)} rows={6} placeholder='Paste JSON array or {"rules": [...]}' className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 font-mono" />
                  <button onClick={handleImportRules} disabled={loading || !importText.trim()} className="w-full px-4 py-2.5 rounded-lg border border-suse-green text-suse-green font-medium disabled:opacity-50 inline-flex items-center justify-center gap-2">
                    <DocumentArrowUpIcon className="w-4 h-4" /> Import Rules
                  </button>
                </div>
              </div>
              <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  <h3 className="font-semibold text-gray-900">Rules</h3>
                  <input value={ruleFilter} onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleFilter(e.target.value)} placeholder="Filter by id, name, category, pattern" className="w-full md:w-80 px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                </div>
                <div className="divide-y divide-gray-100 max-h-[60vh] overflow-auto">
                  {filteredRules.map((rule) => (
                    <div key={rule.id} className="px-5 py-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-gray-900">{rule.name}</span>
                            <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-700 font-mono">{rule.id}</span>
                            <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">{rule.category}</span>
                            <span className={`px-2 py-0.5 rounded-full text-xs ${rule.enabled ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{rule.enabled ? 'enabled' : 'disabled'}</span>
                            {rule.is_builtin ? <span className="px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700">built-in</span> : <span className="px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700">custom</span>}
                          </div>
                          <p className="mt-2 text-xs text-gray-500 font-mono break-all">{rule.pattern}</p>
                          <p className="mt-1 text-xs text-gray-400">strategy={rule.strategy} · weight={rule.weight} · placeholder={rule.placeholder}</p>
                        </div>
                        <div className="flex flex-wrap gap-2 justify-end">
                          <button onClick={() => handleEditRule(rule)} className="px-3 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50">Edit</button>
                          <button onClick={() => handleToggleRule(rule.id)} className="px-3 py-2 rounded-lg border border-amber-200 text-sm text-amber-700 hover:bg-amber-50">Toggle</button>
                          {!rule.is_builtin && (
                            <button onClick={() => handleDeleteRule(rule.id)} className="px-3 py-2 rounded-lg border border-red-200 text-sm text-red-600 hover:bg-red-50">Delete</button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : activeTab === 'suggestions' ? (
            <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <h3 className="font-semibold text-gray-900">Rule Approvals</h3>
                <select value={suggestionStatus} onChange={(e: ChangeEvent<HTMLSelectElement>) => setSuggestionStatus(e.target.value as typeof suggestionStatus)} className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white w-full md:w-48">
                  <option value="pending">pending</option>
                  <option value="approved">approved</option>
                  <option value="rejected">rejected</option>
                  <option value="all">all</option>
                </select>
              </div>
              <div className="divide-y divide-gray-100 max-h-[68vh] overflow-auto">
                {suggestions.map((suggestion) => (
                  <div key={suggestion.id} className="px-5 py-4 space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-gray-900">Suggestion #{suggestion.id}</span>
                      <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700">{suggestion.action}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs ${suggestion.status === 'pending' ? 'bg-amber-100 text-amber-700' : suggestion.status === 'approved' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{suggestion.status}</span>
                    </div>
                    <div className="text-sm text-gray-700 grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div>Rule ID: <span className="font-mono">{suggestion.rule_id || 'new rule'}</span></div>
                      <div>Submitted by: <span className="font-medium">{suggestion.submitted_by || 'anonymous'}</span></div>
                      {suggestion.name && <div>Name: <span className="font-medium">{suggestion.name}</span></div>}
                      {suggestion.category && <div>Category: <span className="font-medium">{suggestion.category}</span></div>}
                    </div>
                    {suggestion.pattern && <pre className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-auto text-gray-700">{suggestion.pattern}</pre>}
                    {suggestion.reason && <p className="text-sm text-gray-600">Reason: {suggestion.reason}</p>}
                    {suggestion.status === 'pending' && (
                      <div className="flex gap-2">
                        <button onClick={() => handleReviewSuggestion(suggestion.id, 'approve')} className="px-4 py-2 rounded-lg bg-suse-green text-white text-sm font-medium">Approve</button>
                        <button onClick={() => handleReviewSuggestion(suggestion.id, 'reject')} className="px-4 py-2 rounded-lg border border-red-200 text-red-600 text-sm font-medium hover:bg-red-50">Reject</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-gray-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <h3 className="font-semibold text-gray-900">Rule Change History</h3>
                <div className="flex gap-3 w-full md:w-auto">
                  <input value={historyRuleId} onChange={(e: ChangeEvent<HTMLInputElement>) => setHistoryRuleId(e.target.value)} placeholder="Filter by rule_id" className="w-full md:w-60 px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900" />
                  <button onClick={loadHistory} className="px-4 py-2.5 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50 inline-flex items-center gap-2">
                    <ArrowPathIcon className="w-4 h-4" /> Load
                  </button>
                </div>
              </div>
              <div className="divide-y divide-gray-100 max-h-[68vh] overflow-auto">
                {historyEntries.map((entry) => (
                  <div key={entry.id} className="px-5 py-4 space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-gray-900">{entry.rule_id}</span>
                      <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-700">{entry.action}</span>
                      <span className="text-xs text-gray-500">by {entry.changed_by}</span>
                      <span className="text-xs text-gray-400">{entry.changed_at}</span>
                    </div>
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Old Value</p>
                        <pre className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-auto text-gray-700">{prettyJson(entry.old_value)}</pre>
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-gray-500 uppercase mb-1">New Value</p>
                        <pre className="text-xs bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-auto text-gray-700">{prettyJson(entry.new_value)}</pre>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {loading && (
          <div className="absolute bottom-4 right-4 bg-suse-green text-white text-sm px-4 py-2 rounded-full shadow-lg inline-flex items-center gap-2">
            <SparklesIcon className="w-4 h-4" /> Working…
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
