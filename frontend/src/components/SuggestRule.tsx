import { useState, useEffect, type ChangeEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LightBulbIcon,
  SparklesIcon,
  XMarkIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import { submitRuleSuggestion, getRulesDetailed, getMyKeyInfo, getSessionToken, RuleDetail } from '../services/api';
import { useModalA11y } from '../hooks/useModalA11y';
import { useAiRegex } from '../hooks/useAiRegex';
import AiRegexPanel from './AiRegexPanel';

interface SuggestRuleProps {
  onClose: () => void;
}

type SuggestionAction = 'create' | 'modify' | 'disable';

export default function SuggestRule({ onClose }: SuggestRuleProps) {
  const dialogRef = useModalA11y(onClose);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isOrgOwner, setIsOrgOwner] = useState(false);
  const [action, setAction] = useState<SuggestionAction>('create');
  const [ruleId, setRuleId] = useState('');
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [pattern, setPattern] = useState('');
  const [flags, setFlags] = useState('');
  const [strategy, setStrategy] = useState('placeholder');
  const [placeholder, setPlaceholder] = useState('[MASKED]');
  const [weight, setWeight] = useState(5);
  const [reason, setReason] = useState('');

  const [existingRules, setExistingRules] = useState<RuleDetail[]>([]);
  const [rulesLoaded, setRulesLoaded] = useState(false);
  const [ruleTab, setRuleTab] = useState<'public' | 'private'>('public');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const ai = useAiRegex({
    onApply: (res) => {
      setPattern(res.pattern);
      setName((prev) => prev.trim() ? prev : (res.suggested_name ?? prev));
      setCategory((prev) => prev.trim() ? prev : (res.suggested_category ?? prev));
    },
    onSuccess: (message) => {
      setInfo(message);
      window.setTimeout(() => setInfo(null), 2500);
    },
  });

  useEffect(() => {
    if (!getSessionToken()) return;
    getMyKeyInfo().then((info) => {
      setIsAdmin(info.role === 'admin');
      setIsOrgOwner(info.is_org_owner === true);
    }).catch(() => {});
  }, []);

  const loadExistingRules = async () => {
    if (rulesLoaded) return;
    try {
      const data = await getRulesDetailed();
      setExistingRules(data.rules || []);
      setRulesLoaded(true);
    } catch {
      // ignore — user can still type manually
    }
  };

  const handleActionChange = (newAction: SuggestionAction) => {
    setAction(newAction);
    if (newAction !== 'create') {
      loadExistingRules();
    }
  };

  const handleSubmit = async () => {
    if (!reason.trim()) {
      setError('Please provide a reason for your suggestion');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await submitRuleSuggestion({
        rule_id: action !== 'create' ? ruleId || null : null,
        action,
        name: name || null,
        category: category || null,
        pattern: pattern || null,
        flags: flags || null,
        strategy: strategy || null,
        placeholder: placeholder || null,
        weight: weight ?? null,
        reason: reason.trim(),
      });
      setSubmitted(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to submit suggestion');
    } finally {
      setLoading(false);
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
        aria-label="Suggest a Rule Change"
        tabIndex={-1}
        initial={{ scale: 0.96, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.96, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-auto outline-none"
      >
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-amber-50 rounded-lg">
              <LightBulbIcon className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">Suggest a Rule Change</h2>
              <p className="text-xs text-gray-500">
                {isAdmin || isOrgOwner
                  ? 'You can review and approve suggestions directly'
                  : 'Your suggestion will be reviewed by your org owner or admin'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:bg-gray-100 transition-colors">
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {submitted ? (
            <div className="py-8 text-center space-y-3">
              <CheckCircleIcon className="w-12 h-12 text-green-500 mx-auto" />
              <p className="text-lg font-semibold text-gray-900">Suggestion Submitted</p>
              <p className="text-sm text-gray-500">
                {isAdmin || isOrgOwner
                  ? 'You can review and approve it now in the Rule Approvals tab.'
                  : 'Your org owner or admin will review your suggestion. Thank you!'}
              </p>
              <button onClick={onClose} className="mt-4 px-6 py-2.5 bg-suse-green text-white rounded-lg font-medium">
                Close
              </button>
            </div>
          ) : (
            <>
              {error && (
                <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm border border-red-200">{error}</div>
              )}
              {info && (
                <div className="p-3 rounded-lg bg-green-50 text-green-700 text-sm border border-green-200">{info}</div>
              )}

              {/* Action type */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">What would you like to do?</label>
                <div className="flex gap-2">
                  {(['create', 'modify', 'disable'] as const).map((a) => (
                    <button
                      key={a}
                      onClick={() => handleActionChange(a)}
                      className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                        action === a
                          ? 'bg-suse-green text-white border-suse-green'
                          : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                      }`}
                    >
                      {a === 'create' ? 'New Rule' : a === 'modify' ? 'Modify Rule' : 'Disable Rule'}
                    </button>
                  ))}
                </div>
              </div>

              {/* Target rule for modify/disable */}
              {action !== 'create' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Target Rule</label>
                  {rulesLoaded && existingRules.length > 0 ? (
                    <div className="space-y-2">
                      {/* scope tab picker */}
                      <div className="flex gap-1 p-1 bg-gray-100 rounded-lg">
                        <button
                          onClick={() => { setRuleTab('public'); setRuleId(''); }}
                          className={`flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                            ruleTab === 'public' ? 'bg-white shadow text-suse-green' : 'text-gray-500 hover:text-gray-700'
                          }`}
                        >
                          🌐 Public
                          <span className="ml-1 text-gray-400">
                            ({existingRules.filter(r => r.scope === 'system' || r.scope === 'org').length})
                          </span>
                        </button>
                        <button
                          onClick={() => { setRuleTab('private'); setRuleId(''); }}
                          className={`flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                            ruleTab === 'private' ? 'bg-white shadow text-suse-green' : 'text-gray-500 hover:text-gray-700'
                          }`}
                        >
                          🔒 Private
                          <span className="ml-1 text-gray-400">
                            ({existingRules.filter(r => r.scope === 'private').length})
                          </span>
                        </button>
                      </div>
                      <select
                        value={ruleId}
                        onChange={(e: ChangeEvent<HTMLSelectElement>) => setRuleId(e.target.value)}
                        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white"
                      >
                        <option value="">— Select a rule —</option>
                        {existingRules
                          .filter(r => ruleTab === 'public'
                            ? (r.scope === 'system' || r.scope === 'org')
                            : r.scope === 'private'
                          )
                          .map(r => (
                            <option key={r.id} value={r.id}>
                              {ruleTab === 'public'
                                ? `${r.scope === 'system' ? '🌐' : '🏢'} ${r.id} — ${r.name}`
                                : `🔒 ${r.id} — ${r.name}`
                              }
                            </option>
                          ))}
                      </select>
                    </div>
                  ) : (
                    <input
                      value={ruleId}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => setRuleId(e.target.value)}
                      placeholder="rule_id"
                      className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900"
                    />
                  )}
                </div>
              )}

              {/* Rule details for create/modify */}
              {action !== 'disable' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Rule Name</label>
                      <input value={name} onChange={(e: ChangeEvent<HTMLInputElement>) => setName(e.target.value)} placeholder="e.g. AWS Secret Key" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Category</label>
                      <input value={category} onChange={(e: ChangeEvent<HTMLInputElement>) => setCategory(e.target.value)} placeholder="e.g. cloud, pii" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900" />
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <label className="block text-xs font-medium text-gray-500">Regex Pattern</label>
                      <button
                        type="button"
                        onClick={ai.openPanel}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-violet-500 to-purple-600 text-white text-xs font-medium hover:from-violet-600 hover:to-purple-700 transition-all"
                      >
                        <SparklesIcon className="w-3.5 h-3.5" />
                        Generate with AI
                      </button>
                    </div>
                    <textarea value={pattern} onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setPattern(e.target.value)} placeholder="e.g. AKIA[0-9A-Z]{16}" rows={3} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 font-mono" />
                  </div>
                  <AnimatePresence>
                    {ai.showAiPanel && <AiRegexPanel {...ai} />}
                  </AnimatePresence>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Strategy</label>
                      <select value={strategy} onChange={(e: ChangeEvent<HTMLSelectElement>) => setStrategy(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white">
                        <option value="placeholder">placeholder</option>
                        <option value="partial">partial</option>
                        <option value="asterisk">asterisk</option>
                        <option value="hash">hash</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Placeholder</label>
                      <input value={placeholder} onChange={(e: ChangeEvent<HTMLInputElement>) => setPlaceholder(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-500 mb-1">Weight</label>
                      <input type="number" min={0} max={100} value={weight} onChange={(e: ChangeEvent<HTMLInputElement>) => setWeight(Number(e.target.value) || 0)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Regex Flags</label>
                    <input value={flags} onChange={(e: ChangeEvent<HTMLInputElement>) => setFlags(e.target.value)} placeholder="e.g. IGNORECASE" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900" />
                  </div>
                </>
              )}

              {/* Reason — always required */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Reason <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={reason}
                  onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setReason(e.target.value)}
                  placeholder="Explain why this rule change is needed..."
                  rows={3}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900"
                />
              </div>

              <button
                onClick={handleSubmit}
                disabled={loading || !reason.trim() || (action !== 'create' && !ruleId)}
                className="w-full px-4 py-2.5 rounded-lg bg-suse-green text-white font-medium disabled:opacity-50 transition-colors"
              >
                {loading ? 'Submitting…' : 'Submit Suggestion'}
              </button>
            </>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
