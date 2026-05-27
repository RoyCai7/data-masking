/**
 * AiRegexPanel
 *
 * Self-contained UI for AI-powered regex generation.
 * All state and logic live in the `useAiRegex` hook; this component only renders.
 * Use <AnimatePresence> in the parent to animate mount/unmount.
 */
import { type ChangeEvent, type RefObject } from 'react';
import { motion } from 'framer-motion';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  CpuChipIcon,
  SparklesIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import type { UseAiRegexReturn } from '../hooks/useAiRegex';

type AiRegexPanelProps = Pick<
  UseAiRegexReturn,
  | 'aiPanelRef'
  | 'aiProvider'
  | 'aiDescription'
  | 'aiContext'
  | 'aiModel'
  | 'aiModels'
  | 'aiModelsLoading'
  | 'aiModelsError'
  | 'aiProviders'
  | 'aiProvidersLoading'
  | 'aiGenerating'
  | 'aiResult'
  | 'aiError'
  | 'closePanel'
  | 'switchProvider'
  | 'setAiDescription'
  | 'setAiContext'
  | 'setAiModel'
  | 'generate'
  | 'applyPattern'
>;

export default function AiRegexPanel({
  aiPanelRef,
  aiProvider,
  aiDescription,
  aiContext,
  aiModel,
  aiModels,
  aiModelsLoading,
  aiModelsError,
  aiProviders,
  aiProvidersLoading,
  aiGenerating,
  aiResult,
  aiError,
  closePanel,
  switchProvider,
  setAiDescription,
  setAiContext,
  setAiModel,
  generate,
  applyPattern,
}: AiRegexPanelProps) {
  return (
    <motion.div
      ref={aiPanelRef as RefObject<HTMLDivElement>}
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className="overflow-hidden"
    >
      <div className="border border-violet-200 bg-violet-50 rounded-xl p-4 space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CpuChipIcon className="w-4 h-4 text-violet-600" />
            <span className="text-sm font-semibold text-violet-800">AI Regex Generator</span>
          </div>
          <button
            type="button"
            onClick={closePanel}
            className="p-1 rounded-md hover:bg-violet-100 text-violet-500 transition-colors"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Provider toggle */}
        <div className="flex rounded-lg overflow-hidden border border-violet-300 text-xs font-medium">
          <button
            type="button"
            onClick={() => switchProvider('ollama')}
            className={`flex-1 py-2 ${aiProvider === 'ollama' ? 'bg-violet-600 text-white' : 'bg-white text-violet-700'}`}
          >
            Ollama
          </button>
          <button
            type="button"
            onClick={() => switchProvider('opencode')}
            className={`flex-1 py-2 ${aiProvider === 'opencode' ? 'bg-violet-600 text-white' : 'bg-white text-violet-700'}`}
          >
            OpenCode (oc)
          </button>
        </div>

        {/* Provider selector */}
        <div>
          <label className="block text-xs font-medium text-violet-700 mb-1">Provider</label>
          {aiProvidersLoading ? (
            <div className="text-xs text-violet-500 animate-pulse">Loading providers…</div>
          ) : (
            <select
              value={aiProvider}
              onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                switchProvider(e.target.value as 'ollama' | 'opencode')
              }
              className="w-full px-3 py-2 border border-violet-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-violet-400 focus:outline-none"
            >
              {aiProviders.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          )}
          {aiProviders.find((p) => p.id === aiProvider) && (
            <p className="text-xs text-violet-500 mt-1">
              {aiProviders.find((p) => p.id === aiProvider)?.note}
            </p>
          )}
        </div>

        {/* Ollama: model list */}
        {aiProvider === 'ollama' && (
          <div>
            <label className="block text-xs font-medium text-violet-700 mb-1">Local Model (Ollama)</label>
            {aiModelsLoading ? (
              <div className="text-xs text-violet-500 animate-pulse">Loading models…</div>
            ) : aiModelsError ? (
              <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center justify-between">
                <span>{aiModelsError}</span>
                <button
                  type="button"
                  onClick={() => switchProvider('ollama')}
                  className="underline text-red-700 font-medium ml-2"
                >
                  Retry
                </button>
              </div>
            ) : aiModels.length === 0 ? (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                No models found. Run{' '}
                <code className="font-mono bg-amber-100 px-1 rounded">ollama pull gemma3:4b</code>{' '}
                to get started.
              </div>
            ) : (
              <select
                value={aiModel}
                onChange={(e: ChangeEvent<HTMLSelectElement>) => setAiModel(e.target.value)}
                className="w-full px-3 py-2 border border-violet-300 rounded-lg text-sm text-gray-900 bg-white focus:ring-2 focus:ring-violet-400 focus:outline-none"
              >
                {aiModels.map((m) => (
                  <option key={m.name} value={m.name}>{m.name}</option>
                ))}
              </select>
            )}
            <p className="text-xs text-violet-400 mt-1">
              Default:{' '}
              <span className="font-mono font-semibold text-violet-600">gemma3:4b</span> · best
              quality:{' '}
              <span className="font-mono font-semibold text-violet-600">gemma3:12b</span>
            </p>
          </div>
        )}

        {/* OpenCode: manual model input */}
        {aiProvider === 'opencode' && (
          <div>
            <label className="block text-xs font-medium text-violet-700 mb-1">OpenCode Model</label>
            <input
              value={aiModel}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setAiModel(e.target.value)}
              placeholder="e.g. gemma3:4b"
              className="w-full px-3 py-2 border border-violet-300 rounded-lg text-sm text-gray-900 focus:ring-2 focus:ring-violet-400 focus:outline-none"
            />
            <p className="text-xs text-violet-400 mt-1">
              OpenCode uses the local HTTP service configured in the backend.
            </p>
          </div>
        )}

        {/* Description */}
        <div>
          <label className="block text-xs font-medium text-violet-700 mb-1">
            Describe what to match
          </label>
          <textarea
            value={aiDescription}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setAiDescription(e.target.value)}
            placeholder="e.g. IPv4 addresses in CIDR notation like 192.168.1.0/24"
            rows={3}
            className="w-full px-3 py-2 border border-violet-300 rounded-lg text-sm text-gray-900 focus:ring-2 focus:ring-violet-400 focus:outline-none resize-none"
          />
        </div>

        {/* Context hint */}
        <div>
          <label className="block text-xs font-medium text-violet-700 mb-1">
            Context hint{' '}
            <span className="font-normal text-violet-400">(optional)</span>
          </label>
          <input
            value={aiContext}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setAiContext(e.target.value)}
            placeholder="e.g. for Linux log files, Python re module"
            className="w-full px-3 py-2 border border-violet-300 rounded-lg text-sm text-gray-900 focus:ring-2 focus:ring-violet-400 focus:outline-none"
          />
        </div>

        {/* Generate button */}
        <button
          type="button"
          onClick={generate}
          disabled={
            aiGenerating ||
            !aiDescription.trim() ||
            !aiModel.trim() ||
            (aiProvider === 'ollama' && aiModels.length === 0)
          }
          className="w-full px-4 py-2.5 rounded-lg bg-gradient-to-r from-violet-500 to-purple-600 text-white font-medium text-sm disabled:opacity-50 inline-flex items-center justify-center gap-2 hover:from-violet-600 hover:to-purple-700 transition-all"
        >
          {aiGenerating ? (
            <><ArrowPathIcon className="w-4 h-4 animate-spin" /> Generating…</>
          ) : (
            <><SparklesIcon className="w-4 h-4" /> Generate Regex</>
          )}
        </button>

        {/* Error */}
        {aiError && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {aiError}
          </div>
        )}

        {/* Result */}
        {aiResult && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-2"
          >
            <div className="bg-white border border-violet-200 rounded-lg p-3 space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-violet-700 uppercase tracking-wide">
                  Generated Pattern
                </p>
                {aiResult.provider && (
                  <span className="text-xs text-violet-400 font-mono">{aiResult.provider}</span>
                )}
              </div>
              <code className="block text-xs font-mono text-gray-800 break-all whitespace-pre-wrap">
                {aiResult.pattern}
              </code>
              {aiResult.explanation && (
                <p className="text-xs text-gray-500 italic border-t border-violet-100 pt-2">
                  {aiResult.explanation}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={applyPattern}
              className="w-full px-4 py-2 rounded-lg bg-suse-green text-white font-medium text-sm inline-flex items-center justify-center gap-2 hover:bg-suse-green-dark transition-colors"
            >
              <CheckCircleIcon className="w-4 h-4" />
              Apply Pattern
            </button>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
