import { useState, useEffect, useCallback } from 'react';
import { XMarkIcon, ClipboardIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import {
  getMyOrg, createOrg, refreshInviteCode, joinOrg, leaveOrg, getMyKeyInfo,
  Organization,
} from '../services/api';

interface MyOrgProps {
  onClose: () => void;
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).catch(() => {
    const el = document.createElement('textarea');
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
  });
}

export default function MyOrg({ onClose }: MyOrgProps) {
  const [org, setOrg] = useState<Organization | null>(null);
  const [myName, setMyName] = useState('');
  const [myKeyPrefix, setMyKeyPrefix] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create org form
  const [newOrgName, setNewOrgName] = useState('');

  // Join form
  const [inviteInput, setInviteInput] = useState('');

  const showMsg = (msg: string) => {
    setSuccess(msg);
    window.setTimeout(() => setSuccess(''), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [keyInfo, myOrg] = await Promise.all([getMyKeyInfo(), getMyOrg()]);
      setMyName(keyInfo.name ?? '');
      // key_preview is "dms_xxxx..." — strip trailing dots to get the prefix
      setMyKeyPrefix((keyInfo.key_preview ?? '').replace(/\.+$/, ''));
      setOrg(myOrg);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Owner = caller's key_prefix matches org.owner_key_prefix (server-side ground truth)
  // Fall back to name match for orgs created before this change
  const isOwner = org && (
    (myKeyPrefix && org.owner_key_prefix && myKeyPrefix === org.owner_key_prefix) ||
    (!org.owner_key_prefix && myName && org.owner === myName)
  );
  const inDefaultOrg = !org || org.id === 'default';

  const handleCreateOrg = async () => {
    if (!newOrgName.trim()) return;
    setLoading(true); setError('');
    // Auto-generate slug: lowercase, spaces→hyphens, strip special chars, add short random suffix
    const base = newOrgName.trim().toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '').slice(0, 24);
    const slug = `${base}-${Math.random().toString(36).slice(2, 6)}`;
    try {
      await createOrg({ id: slug, name: newOrgName.trim() });
      setNewOrgName('');
      showMsg('Organization created! You have been moved to it.');
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create org');
    } finally { setLoading(false); }
  };

  const handleRefreshCode = async () => {
    if (!org) return;
    setLoading(true); setError('');
    try {
      const res = await refreshInviteCode(org.id);
      showMsg('Invite code refreshed');
      setOrg(res.org);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to refresh');
    } finally { setLoading(false); }
  };

  const handleLeave = async () => {
    if (!window.confirm('Leave this organization and return to default?')) return;
    setLoading(true); setError('');
    try {
      const res = await leaveOrg();
      showMsg(res.message + ' Reload to apply.');
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to leave org');
    } finally { setLoading(false); }
  };

  const handleJoin = async () => {
    if (!inviteInput.trim()) return;
    setLoading(true); setError('');
    try {
      const res = await joinOrg(inviteInput.trim());
      setInviteInput('');
      showMsg(`Joined "${res.org_name}" successfully! Reload the page to apply.`);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Invalid invite code');
    } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-bold text-gray-900">🏢 My Organization</h2>
            <p className="text-xs text-gray-500 mt-0.5">Manage your team workspace</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100">
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* Messages */}
          {error && <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">{error}</div>}
          {success && <div className="px-4 py-3 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700">{success}</div>}

          {loading && !org && (
            <div className="text-center py-8 text-gray-400 text-sm">Loading…</div>
          )}

          {/* Current org info */}
          {org && (
            <div className={`rounded-2xl border p-5 space-y-3 ${org.id === 'default' ? 'border-gray-200 bg-gray-50' : 'border-suse-green/30 bg-green-50/30'}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide font-medium">Current Organization</p>
                  <p className="text-lg font-bold text-gray-900 mt-0.5">{org.name}</p>
                  <p className="text-xs text-gray-400 font-mono mt-0.5">{org.id}</p>
                </div>
                {org.id !== 'default' && (
                  <span className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${isOwner ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'}`}>
                    {isOwner ? '👑 Owner' : '👤 Member'}
                  </span>
                )}
              </div>

              {/* Invite code — visible to owner */}
              {org.id !== 'default' && isOwner && (
                <div className="pt-3 border-t border-gray-200 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-gray-700">Invite Code — share with teammates</p>
                    {org.invite_code_expires_at && (
                      <p className="text-xs text-gray-400">
                        expires {new Date(org.invite_code_expires_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  {org.invite_code ? (
                    <div className="flex items-center gap-2">
                      <code className="flex-1 px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm font-mono text-gray-800 select-all">
                        {org.invite_code}
                      </code>
                      <button
                        onClick={() => { copyToClipboard(org.invite_code!); showMsg('Copied!'); }}
                        className="p-2 rounded-lg border border-gray-200 text-gray-500 hover:text-suse-green hover:border-suse-green/50"
                        title="Copy invite code"
                      >
                        <ClipboardIcon className="w-4 h-4" />
                      </button>
                      <button
                        onClick={handleRefreshCode}
                        disabled={loading}
                        className="p-2 rounded-lg border border-gray-200 text-gray-500 hover:text-orange-600 hover:border-orange-300"
                        title="Invalidate old code and generate new one"
                      >
                        <ArrowPathIcon className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                      </button>
                    </div>
                  ) : (
                    <button onClick={handleRefreshCode} disabled={loading} className="text-sm text-suse-green hover:underline">
                      Generate invite code
                    </button>
                  )}
                </div>
              )}

              {/* Non-owner member in a real org */}
              {org.id !== 'default' && !isOwner && (
                <div className="pt-2 border-t border-gray-200 space-y-2">
                  <p className="text-xs text-gray-500">
                    Contact the org owner <span className="font-medium">{org.owner || 'admin'}</span> for the invite code.
                  </p>
                  <button
                    onClick={handleLeave}
                    disabled={loading}
                    className="text-xs text-red-600 hover:text-red-700 hover:underline disabled:opacity-50"
                  >
                    Leave organization
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Create org — only shown when in default / no org */}
          {inDefaultOrg && (
            <div className="rounded-2xl border border-dashed border-gray-300 p-5 space-y-3">
              <div>
                <p className="text-sm font-semibold text-gray-800">Create Your Organization</p>
                <p className="text-xs text-gray-500 mt-0.5">Start a private workspace for your team. You can invite others with a code.</p>
              </div>
              <input
                value={newOrgName}
                onChange={e => setNewOrgName(e.target.value)}
                placeholder="Organization name, e.g. My Team"
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900"
                onKeyDown={e => e.key === 'Enter' && handleCreateOrg()}
              />
              <button
                onClick={handleCreateOrg}
                disabled={loading || !newOrgName.trim()}
                className="w-full px-4 py-2.5 rounded-lg bg-suse-green text-white text-sm font-medium disabled:opacity-50"
              >
                {loading ? 'Creating…' : '✨ Create Organization'}
              </button>
            </div>
          )}

          {/* Join org via invite code */}
          <div className="rounded-2xl border border-gray-200 p-5 space-y-3">
            <div>
              <p className="text-sm font-semibold text-gray-800">Join Another Organization</p>
              <p className="text-xs text-gray-500 mt-0.5">Enter an invite code from an org owner to switch your workspace.</p>
            </div>
            <div className="flex gap-2">
              <input
                value={inviteInput}
                onChange={e => setInviteInput(e.target.value)}
                placeholder="Paste invite code here"
                onKeyDown={e => e.key === 'Enter' && handleJoin()}
                className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm text-gray-900 font-mono"
              />
              <button
                onClick={handleJoin}
                disabled={loading || !inviteInput.trim()}
                className="px-4 py-2.5 rounded-lg bg-suse-green text-white text-sm font-medium disabled:opacity-50"
              >
                Join
              </button>
            </div>
          </div>
        </div>

        <div className="px-6 py-3 border-t border-gray-100 text-xs text-gray-400 text-center">
          Changing org takes effect on your next action. Reload to refresh rule visibility.
        </div>
      </div>
    </div>
  );
}
