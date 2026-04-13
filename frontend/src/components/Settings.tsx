import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  KeyIcon,
  ArrowPathIcon,
  ClipboardIcon,
  CheckIcon,
  EyeIcon,
  EyeSlashIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import {
  getApiKey,
  setApiKey,
  clearApiKey,
  getMyKeyInfo,
  rotateMyKey,
  KeyInfo,
} from '../services/api';

interface SettingsProps {
  onClose: () => void;
}

export default function Settings({ onClose }: SettingsProps) {
  const [apiKey, setApiKeyState] = useState(getApiKey());
  const [showApiKey, setShowApiKey] = useState(false);
  const [keyInfo, setKeyInfo] = useState<KeyInfo | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [isRotating, setIsRotating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  useEffect(() => {
    if (apiKey) {
      fetchKeyInfo();
    }
  }, [apiKey]);

  const fetchKeyInfo = async () => {
    try {
      const info = await getMyKeyInfo();
      setKeyInfo(info);
      setError(null);
    } catch {
      setKeyInfo(null);
    }
  };

  const handleSaveKey = () => {
    setApiKey(apiKey);
    setApiKeyState(apiKey);
    setError(null);
    fetchKeyInfo();
  };

  const handleClearKey = () => {
    clearApiKey();
    setApiKeyState('');
    setKeyInfo(null);
    setNewKey(null);
  };

  const handleRotate = async () => {
    setIsRotating(true);
    setError(null);
    try {
      const result = await rotateMyKey();
      setNewKey(result.new_key);
      setApiKeyState(result.new_key);
      fetchKeyInfo();
      setShowConfirm(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to rotate key');
    } finally {
      setIsRotating(false);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const maskedKey = apiKey
    ? apiKey.substring(0, 8) + '•'.repeat(Math.max(0, apiKey.length - 12)) + apiKey.slice(-4)
    : '';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-white rounded-2xl shadow-xl max-w-lg w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-suse-green-50 rounded-lg">
              <KeyIcon className="w-6 h-6 text-suse-green" />
            </div>
            <h2 className="text-xl font-bold text-gray-900">API Key Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-gray-100 transition-colors"
          >
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Key Input */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              API Key
            </label>
            <div className="flex space-x-2">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKeyState(e.target.value)}
                placeholder="dms_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                className="flex-1 px-4 py-2.5 bg-white text-gray-900 placeholder:text-gray-400 caret-gray-900 border border-gray-300 rounded-lg focus:ring-2 focus:ring-suse-green focus:border-suse-green outline-none transition-all text-sm font-mono"
                style={{ WebkitTextFillColor: '#111827' }}
              />
              <button
                type="button"
                onClick={() => setShowApiKey((value) => !value)}
                className="px-3 py-2.5 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
                title={showApiKey ? 'Hide API key' : 'Show API key'}
              >
                {showApiKey ? (
                  <EyeSlashIcon className="w-5 h-5" />
                ) : (
                  <EyeIcon className="w-5 h-5" />
                )}
              </button>
              <button
                onClick={handleSaveKey}
                className="px-4 py-2.5 bg-suse-green text-white rounded-lg hover:bg-suse-green/90 transition-colors text-sm font-medium"
              >
                Save
              </button>
              {apiKey && (
                <button
                  onClick={handleClearKey}
                  className="px-3 py-2.5 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors text-sm"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Key Info */}
          <AnimatePresence>
            {keyInfo && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="p-4 bg-gray-50 rounded-xl space-y-2"
              >
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-gray-500">Owner:</span>{' '}
                    <span className="font-medium text-gray-900">{keyInfo.name}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Role:</span>{' '}
                    <span className={`font-medium ${keyInfo.role === 'admin' ? 'text-amber-600' : 'text-gray-900'}`}>
                      {keyInfo.role}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Created:</span>{' '}
                    <span className="font-medium text-gray-900">{keyInfo.created_at}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Expires:</span>{' '}
                    <span className="font-medium text-gray-900">{keyInfo.expires_at}</span>
                  </div>
                </div>
                <div className="pt-2 border-t border-gray-200">
                  <span className="text-xs text-gray-400 font-mono">{maskedKey}</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* New Key Display */}
          <AnimatePresence>
            {newKey && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="p-4 bg-green-50 border border-green-200 rounded-xl"
              >
                <div className="flex items-start space-x-2">
                  <CheckIcon className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-green-800">New key generated!</p>
                    <div className="mt-2 flex items-center space-x-2">
                      <code className="flex-1 text-xs bg-white px-3 py-2 rounded border font-mono text-gray-800 break-all">
                        {newKey}
                      </code>
                      <button
                        onClick={() => handleCopy(newKey)}
                        className="p-2 rounded-lg hover:bg-green-100 transition-colors flex-shrink-0"
                        title="Copy to clipboard"
                      >
                        {copied ? (
                          <CheckIcon className="w-4 h-4 text-green-600" />
                        ) : (
                          <ClipboardIcon className="w-4 h-4 text-green-600" />
                        )}
                      </button>
                    </div>
                    <p className="mt-2 text-xs text-green-700">
                      ⚠️ Save this key now — it will not be shown again!
                      The key has been auto-saved to your browser.
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Rotate Button */}
          {keyInfo && (
            <div className="pt-2">
              {!showConfirm ? (
                <button
                  onClick={() => setShowConfirm(true)}
                  className="flex items-center space-x-2 px-4 py-2.5 border-2 border-amber-400 text-amber-700 rounded-lg hover:bg-amber-50 transition-colors text-sm font-medium w-full justify-center"
                >
                  <ArrowPathIcon className="w-4 h-4" />
                  <span>Rotate My API Key</span>
                </button>
              ) : (
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl space-y-3">
                  <div className="flex items-start space-x-2">
                    <ExclamationTriangleIcon className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-amber-800">Are you sure?</p>
                      <p className="text-xs text-amber-700 mt-1">
                        Your current key will be permanently disabled. A new key will be generated
                        and auto-saved to your browser. Any other clients using the old key will stop working.
                      </p>
                    </div>
                  </div>
                  <div className="flex space-x-2">
                    <button
                      onClick={handleRotate}
                      disabled={isRotating}
                      className="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors text-sm font-medium disabled:opacity-50"
                    >
                      {isRotating ? (
                        <>
                          <ArrowPathIcon className="w-4 h-4 animate-spin" />
                          <span>Rotating...</span>
                        </>
                      ) : (
                        <span>Yes, Rotate Key</span>
                      )}
                    </button>
                    <button
                      onClick={() => setShowConfirm(false)}
                      className="px-4 py-2 border border-gray-300 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Help Text */}
          <p className="text-xs text-gray-400 mt-4">
            Don't have a key? Ask your admin or run: <code className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">python generate_key.py create --name "Your Name"</code>
          </p>
        </div>
      </motion.div>
    </motion.div>
  );
}
