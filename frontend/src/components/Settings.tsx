import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowPathIcon,
  CheckIcon,
  ClipboardIcon,
  KeyIcon,
  PlusIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import {
  AccountTokenInfo,
  KeyInfo,
  clearSessionToken,
  createAccountToken,
  disableAccountToken,
  forgotPassword,
  getMyKeyInfo,
  getSessionToken,
  listAccountTokens,
  loginAccount,
  logoutAccount,
  registerAccount,
  resetPassword,
  verifyEmail,
} from '../services/api';
import { useModalA11y } from '../hooks/useModalA11y';

interface SettingsProps {
  onClose: () => void;
}

type AuthMode = 'login' | 'register' | 'forgot' | 'reset' | 'verify';

export default function Settings({ onClose }: SettingsProps) {
  const dialogRef = useModalA11y(onClose);
  const params = new URLSearchParams(window.location.search);
  const initialResetToken = params.get('reset_token') || '';
  const initialVerifyToken = params.get('verify_token') || '';
  const [mode, setMode] = useState<AuthMode>(initialVerifyToken ? 'verify' : initialResetToken ? 'reset' : 'login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [resetToken] = useState(initialResetToken);
  const [verifyToken] = useState(initialVerifyToken);
  const [keyInfo, setKeyInfo] = useState<KeyInfo | null>(null);
  const [tokens, setTokens] = useState<AccountTokenInfo[]>([]);
  const [tokenName, setTokenName] = useState('default-api-token');
  const [newApiToken, setNewApiToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const signedIn = Boolean(getSessionToken() && keyInfo);

  useEffect(() => {
    if (getSessionToken()) {
      refreshAccount();
    } else if (verifyToken) {
      handleVerifyEmail();
    }
  }, []);

  useEffect(() => {
    setPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setStatus(null);
    setError(null);
  }, [mode]);

  const handleVerifyEmail = async () => {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      await verifyEmail(verifyToken);
      await refreshAccount();
      setStatus('Email activated. You are signed in.');
      window.history.replaceState(null, '', window.location.pathname);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to activate email');
    } finally {
      setLoading(false);
    }
  };

  const refreshAccount = async () => {
    try {
      const [info, tokenList] = await Promise.all([getMyKeyInfo(), listAccountTokens()]);
      setKeyInfo(info);
      setTokens(tokenList.tokens || []);
      setError(null);
    } catch {
      setKeyInfo(null);
      setTokens([]);
    }
  };

  const handleAuth = async () => {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      if (mode === 'login') {
        await loginAccount({ email, password });
        await refreshAccount();
        setStatus('Signed in.');
      } else if (mode === 'register') {
        const result = await registerAccount({ email, password, name });
        if (result.email_sent) {
          setStatus(`Account created. Activation email sent to ${result.email}.`);
        } else {
          setError(`Account created, but activation email was not sent: ${result.delivery_detail}`);
        }
      } else if (mode === 'forgot') {
        const result = await forgotPassword(email);
        if (result.email_sent) {
          setStatus(`Password reset email sent to ${result.email}.`);
        } else {
          setError(`Password reset email was not sent: ${result.delivery_detail}`);
        }
      } else if (mode === 'reset') {
        if (newPassword !== confirmPassword) {
          setError('Passwords do not match');
          return;
        }
        await resetPassword(resetToken, newPassword);
        setStatus('Password reset. Sign in with the new password.');
        setPassword('');
        setNewPassword('');
        setConfirmPassword('');
        setMode('login');
        window.history.replaceState(null, '', window.location.pathname);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Request failed');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    setLoading(true);
    try {
      await logoutAccount();
    } catch {
      clearSessionToken();
    } finally {
      setKeyInfo(null);
      setTokens([]);
      setNewApiToken(null);
      setLoading(false);
    }
  };

  const handleCreateToken = async () => {
    setLoading(true);
    setError(null);
    setStatus(null);
    try {
      const result = await createAccountToken({ name: tokenName || 'api-token', expires_days: 365 });
      setNewApiToken(result.key);
      setStatus('API token created. Save it now; it will only be shown once.');
      await refreshAccount();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create API token');
    } finally {
      setLoading(false);
    }
  };

  const handleDisableToken = async (tokenId: number) => {
    setLoading(true);
    setError(null);
    try {
      await disableAccountToken(tokenId);
      await refreshAccount();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to disable API token');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
        aria-label="Account"
        tabIndex={-1}
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-white rounded-xl shadow-xl max-w-2xl w-full p-6 outline-none max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-suse-green-50 rounded-lg">
              <KeyIcon className="w-6 h-6 text-suse-green" />
            </div>
            <h2 className="text-xl font-bold text-gray-900">{signedIn ? 'Account' : 'Sign in'}</h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-full hover:bg-gray-100 transition-colors">
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {!signedIn ? (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-1 rounded-lg bg-gray-100 p-1">
              {(mode === 'reset' ? (['reset'] as AuthMode[]) : mode === 'verify' ? (['verify'] as AuthMode[]) : (['login', 'register', 'forgot'] as AuthMode[])).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    if (item !== 'reset') setMode(item);
                  }}
                  className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${mode === item ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
                >
                  {item === 'login' ? 'Login' : item === 'register' ? 'Register' : item === 'forgot' ? 'Forgot password' : item === 'verify' ? 'Activate email' : 'Set new password'}
                </button>
              ))}
            </div>

            {mode !== 'reset' && (
              <input
                type="email"
                name={`dms-${mode}-email`}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email address"
                autoComplete="off"
                autoCapitalize="none"
                autoCorrect="off"
                className="w-full px-4 py-2.5 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none text-sm"
              />
            )}
            {mode === 'register' && (
              <input
                type="text"
                name="dms-display-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Display name"
                autoComplete="off"
                className="w-full px-4 py-2.5 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none text-sm"
              />
            )}
            {(mode === 'login' || mode === 'register') && (
              <input
                type="password"
                name={`dms-${mode}-password`}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                autoComplete="off"
                className="w-full px-4 py-2.5 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none text-sm"
              />
            )}
            {mode === 'reset' && (
              <>
                <p className="text-sm text-gray-600">
                  Enter a new password for your account.
                </p>
                <input
                  type="password"
                  name="dms-new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="New password"
                  autoComplete="new-password"
                  className="w-full px-4 py-2.5 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none text-sm"
                />
                <input
                  type="password"
                  name="dms-confirm-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                  autoComplete="new-password"
                  className="w-full px-4 py-2.5 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none text-sm"
                />
              </>
            )}
            {mode === 'verify' && (
              <p className="text-sm text-gray-600">
                Activating your email address...
              </p>
            )}
            <button
              type="button"
              onClick={handleAuth}
              disabled={loading || mode === 'verify'}
              className="w-full px-4 py-2.5 bg-suse-green text-white rounded-lg hover:bg-suse-green/90 transition-colors text-sm font-medium disabled:opacity-50"
            >
              {loading ? 'Working...' : mode === 'login' ? 'Login' : mode === 'register' ? 'Create account' : mode === 'forgot' ? 'Send reset email' : mode === 'verify' ? 'Activating...' : 'Reset password'}
            </button>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-gray-500">Name:</span>{' '}
                  <span className="font-medium text-gray-900">{keyInfo?.name}</span>
                </div>
                <div>
                  <span className="text-gray-500">Email:</span>{' '}
                  <span className="font-medium text-gray-900">{keyInfo?.email}</span>
                </div>
                <div>
                  <span className="text-gray-500">Role:</span>{' '}
                  <span className="font-medium text-gray-900">{keyInfo?.role}</span>
                </div>
                <div>
                  <span className="text-gray-500">Org:</span>{' '}
                  <span className="font-medium text-gray-900">{keyInfo?.org_id}</span>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-900">API Tokens</h3>
                <button
                  type="button"
                  onClick={refreshAccount}
                  className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
                  title="Refresh"
                >
                  <ArrowPathIcon className="w-4 h-4 text-gray-600" />
                </button>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  name="dms-token-name"
                  value={tokenName}
                  onChange={(e) => setTokenName(e.target.value)}
                  placeholder="Token name"
                  autoComplete="off"
                  className="flex-1 px-4 py-2.5 bg-white text-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none text-sm"
                />
                <button
                  type="button"
                  onClick={handleCreateToken}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2.5 bg-suse-green text-white rounded-lg hover:bg-suse-green/90 transition-colors text-sm font-medium disabled:opacity-50"
                >
                  <PlusIcon className="w-4 h-4" />
                  <span>Create</span>
                </button>
              </div>

              <AnimatePresence>
                {newApiToken && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="p-3 bg-green-50 border border-green-200 rounded-lg"
                  >
                    <p className="text-sm font-medium text-green-800">New API token</p>
                    <div className="mt-2 flex items-center gap-2">
                      <code className="flex-1 text-xs bg-white px-3 py-2 rounded border font-mono text-gray-800 break-all">
                        {newApiToken}
                      </code>
                      <button
                        type="button"
                        onClick={() => handleCopy(newApiToken)}
                        className="p-2 rounded-lg hover:bg-green-100 transition-colors"
                        title="Copy"
                      >
                        {copied ? <CheckIcon className="w-4 h-4 text-green-700" /> : <ClipboardIcon className="w-4 h-4 text-green-700" />}
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="border border-gray-200 rounded-lg divide-y divide-gray-200">
                {tokens.length === 0 ? (
                  <div className="p-4 text-sm text-gray-500">No API tokens yet.</div>
                ) : tokens.map((token) => (
                  <div key={token.id} className="p-3 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{token.name}</p>
                      <p className="text-xs text-gray-500 font-mono">{token.key_preview} | {token.enabled ? 'active' : 'disabled'} | expires {token.expires_at}</p>
                    </div>
                    {token.enabled && (
                      <button
                        type="button"
                        onClick={() => handleDisableToken(token.id)}
                        className="p-2 rounded-lg hover:bg-red-50 transition-colors"
                        title="Disable token"
                      >
                        <TrashIcon className="w-4 h-4 text-red-600" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={handleLogout}
              disabled={loading}
              className="w-full px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors text-sm font-medium disabled:opacity-50"
            >
              Logout
            </button>
          </div>
        )}

        <AnimatePresence>
          {status && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm break-all"
            >
              {status}
            </motion.div>
          )}
          {error && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}
