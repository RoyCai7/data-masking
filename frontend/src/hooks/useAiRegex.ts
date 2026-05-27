/**
 * useAiRegex
 *
 * Encapsulates all state and side-effects for the AI regex generation panel.
 * AdminConsole (or any consumer) just calls the returned handlers and reads
 * the returned state — zero AI logic leaks up into the parent.
 *
 * Usage:
 *   const ai = useAiRegex({ onApply: (res) => setRuleForm(f => ({ ...f, pattern: res.pattern })) });
 *   <AiRegexPanel {...ai} />
 */
import { useCallback, useRef, useState } from 'react';
import axios, { isAxiosError } from 'axios';
import {
  type LlmProvider,
  type OllamaModel,
  type GenerateRegexResponse,
  generateRegex,
  listLlmModels,
  listLlmProviders,
} from '../services/api';

/** Normalise an unknown axios/fetch error to a human-readable string. */
function errorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    return err.response?.data?.detail ?? err.message ?? fallback;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

export interface AiRegexState {
  /** Whether the panel is visible. */
  showAiPanel: boolean;
  aiProvider: 'ollama' | 'opencode';
  aiDescription: string;
  aiContext: string;
  aiModel: string;
  aiModels: OllamaModel[];
  aiModelsLoading: boolean;
  aiModelsError: string | null;
  aiProviders: LlmProvider[];
  aiProvidersLoading: boolean;
  aiGenerating: boolean;
  /** Full response from the last successful generation. Callers pick whichever fields they need. */
  aiResult: GenerateRegexResponse | null;
  aiError: string | null;
  /** Ref for the panel DOM node (for focus management). */
  aiPanelRef: React.RefObject<HTMLDivElement | null>;
  /** AbortController for the in-flight generate request, if any. */
  _generateAbortRef: React.MutableRefObject<AbortController | null>;
}

export interface AiRegexActions {
  openPanel: () => Promise<void>;
  closePanel: () => void;
  switchProvider: (provider: 'ollama' | 'opencode') => Promise<void>;
  setAiDescription: (v: string) => void;
  setAiContext: (v: string) => void;
  setAiModel: (v: string) => void;
  generate: () => Promise<void>;
  applyPattern: () => void;
}

export type UseAiRegexReturn = AiRegexState & AiRegexActions;

interface UseAiRegexOptions {
  /**
   * Called with the full GenerateRegexResponse when the user clicks "Apply".
   * The hook does not know which fields the parent cares about — that is the
   * caller's responsibility (pattern, suggested_name, suggested_category …).
   */
  onApply: (result: GenerateRegexResponse) => void;
  /** Called with a success message after applying. */
  onSuccess?: (message: string) => void;
}

export function useAiRegex({ onApply, onSuccess }: UseAiRegexOptions): UseAiRegexReturn {
  const aiPanelRef = useRef<HTMLDivElement>(null);
  const _generateAbortRef = useRef<AbortController | null>(null);

  const [showAiPanel, setShowAiPanel] = useState(false);
  const [aiProvider, setAiProvider] = useState<'ollama' | 'opencode'>('ollama');
  const [aiDescription, setAiDescription] = useState('');
  const [aiContext, setAiContext] = useState('');
  const [aiModel, setAiModel] = useState('');
  const [aiModels, setAiModels] = useState<OllamaModel[]>([]);
  const [aiModelsLoading, setAiModelsLoading] = useState(false);
  const [aiModelsError, setAiModelsError] = useState<string | null>(null);
  const [aiProviders, setAiProviders] = useState<LlmProvider[]>([]);
  const [aiProvidersLoading, setAiProvidersLoading] = useState(false);
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiResult, setAiResult] = useState<AiRegexState['aiResult']>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  /** Load Ollama model list. No-op if already loaded. */
  const loadOllamaModels = useCallback(async (currentModel: string) => {
    setAiModelsLoading(true);
    setAiModelsError(null);
    try {
      const data = await listLlmModels();
      setAiModels(data.models);
      if (data.models.length > 0 && !currentModel) {
        setAiModel(data.models[0].name);
      }
    } catch (err: unknown) {
      setAiModelsError(errorMessage(err, 'Cannot connect to Ollama'));
    } finally {
      setAiModelsLoading(false);
    }
  }, []);

  const openPanel = useCallback(async () => {
    setShowAiPanel(true);
    setAiResult(null);
    setAiError(null);

    // Load provider metadata once
    if (aiProviders.length === 0) {
      setAiProvidersLoading(true);
      try {
        const data = await listLlmProviders();
        setAiProviders(data.providers);
      } catch {
        // non-fatal: panel renders with empty provider list
      } finally {
        setAiProvidersLoading(false);
      }
    }

    if (aiProvider === 'ollama' && aiModels.length === 0) {
      await loadOllamaModels(aiModel);
    }
  }, [aiProvider, aiModels.length, aiModel, aiProviders.length, loadOllamaModels]);

  const closePanel = useCallback(() => {
    // Cancel any in-flight generation when the user closes the panel
    _generateAbortRef.current?.abort();
    _generateAbortRef.current = null;
    setShowAiPanel(false);
  }, []);

  const switchProvider = useCallback(async (provider: 'ollama' | 'opencode') => {
    setAiProvider(provider);
    setAiResult(null);
    setAiError(null);

    if (provider === 'ollama' && aiModels.length === 0) {
      await loadOllamaModels(aiModel);
    } else if (provider === 'opencode' && !aiModel) {
      const fallback = aiProviders.find((p) => p.id === 'opencode')?.default_model ?? 'gemma3:4b';
      setAiModel(fallback);
    }
  }, [aiModel, aiModels.length, aiProviders, loadOllamaModels]);

  const generate = useCallback(async () => {
    if (!aiDescription.trim() || !aiModel.trim()) return;

    // Cancel any previous in-flight request
    _generateAbortRef.current?.abort();
    const controller = new AbortController();
    _generateAbortRef.current = controller;

    setAiGenerating(true);
    setAiError(null);
    setAiResult(null);
    try {
      const res = await generateRegex(
        {
          description: aiDescription.trim(),
          model: aiModel.trim(),
          context: aiContext.trim() || undefined,
          provider: aiProvider,
        },
        { signal: controller.signal },
      );
      setAiResult({ pattern: res.pattern, explanation: res.explanation, provider: res.provider, model: res.model, raw_response: res.raw_response, suggested_name: res.suggested_name, suggested_category: res.suggested_category });
    } catch (err: unknown) {
      if (axios.isCancel(err)) return; // panel was closed — silently discard
      setAiError(errorMessage(err, 'Generation failed'));
    } finally {
      setAiGenerating(false);
      _generateAbortRef.current = null;
    }
  }, [aiDescription, aiModel, aiContext, aiProvider]);

  const applyPattern = useCallback(() => {
    if (!aiResult?.pattern) return;
    onApply(aiResult);          // pass the full response; caller decides what to use
    setShowAiPanel(false);
    onSuccess?.('AI-generated pattern applied');
  }, [aiResult, onApply, onSuccess]);

  return {
    // state
    showAiPanel,
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
    aiPanelRef,
    _generateAbortRef,
    // actions
    openPanel,
    closePanel,
    switchProvider,
    setAiDescription,
    setAiContext,
    setAiModel,
    generate,
    applyPattern,
  };
}
