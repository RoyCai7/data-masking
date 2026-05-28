"""
LLM Integration API - local regex generation helpers.

Architecture
============
- Each LLM backend implements the abstract LlmBackend base class.
- Backends register themselves in _REGISTRY keyed by provider-id.
- generate_regex dispatches via the registry: no if/else branching
  required when adding new providers; just subclass and register.

Supported providers
===================
- ollama    : local Ollama server  (HTTP /api/generate)
- opencode  : local OpenCode / any OpenAI-compatible endpoint

Environment variables
=====================
  OLLAMA_BASE_URL         (default: http://10.146.15.188:11434)
  OLLAMA_DEFAULT_MODEL    (default: gemma3:4b)
  OPENCODE_BASE_URL       (default: http://10.146.15.188:3000/v1)
  OPENCODE_DEFAULT_MODEL  (default: gemma3:4b)
  OPENCODE_API_KEY        optional bearer token
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

# ---- Shared HTTP client (singleton, managed by app lifespan) ----------------

_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Return the app-level shared AsyncClient. Raises if not yet initialised."""
    if _http_client is None:
        raise RuntimeError("HTTP client is not initialised — call llm.startup() first")
    return _http_client


async def startup() -> None:
    """Create the shared AsyncClient. Called from app lifespan on startup."""
    global _http_client
    _http_client = httpx.AsyncClient()
    logger.info("llm_startup: shared AsyncClient ready")


async def shutdown() -> None:
    """Close the shared AsyncClient. Called from app lifespan on shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("llm_shutdown: shared AsyncClient closed")


# ---- Config -----------------------------------------------------------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://10.146.15.188:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "gemma3:4b")
OPENCODE_BASE_URL = os.getenv("OPENCODE_BASE_URL", "http://10.146.15.188:3000/v1").rstrip("/")
OPENCODE_DEFAULT_MODEL = os.getenv("OPENCODE_DEFAULT_MODEL", "gemma3:4b")
OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "").strip()


# ---- Prompt helpers ---------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a regex expert assistant. "
    "Your job is to generate a masking rule in strict JSON format. "
    "Rules:\n"
    "1. Output ONLY a single JSON object wrapped in a fenced code block:\n"
    "   ```json\n"
    "   { ... }\n"
    "   ```\n"
    "2. The JSON MUST contain exactly these fields:\n"
    "   - pattern (string): valid Python re-compatible regex, no embedded flags\n"
    "   - flags (string): comma-separated Python re flags if needed, e.g. 'IGNORECASE' or ''\n"
    "   - description (string): one sentence in the user's language explaining what this rule masks\n"
    "   - placeholder (string): replacement token shown after masking, e.g. '[EMAIL]'\n"
    "   - weight (integer 1-10): sensitivity score — 10 = highly sensitive (passwords/IDs), 1 = low risk\n"
    "   - examples (object): {\"match\": [3 example strings the pattern WILL match], "
    "\"no_match\": [2 example strings it will NOT match]}\n"
    "3. Use non-capturing groups (?:...) unless capturing is essential.\n"
    "4. Do NOT add any text outside the JSON code block.\n"
    "5. The pattern must work with Python's re.search().\n"
)


def _build_user_prompt(description: str, context: Optional[str]) -> str:
    hint = f"\nAdditional context: {context}" if context else ""
    return f"Generate a regex pattern that matches: {description}{hint}"


def _extract_regex(text: str) -> Optional[str]:
    """Extract the regex pattern from LLM response text (legacy fallback)."""
    fenced = re.search(r"```(?:regex|python|text)?\s*\n?(.*?)```", text, re.DOTALL)
    if fenced:
        c = fenced.group(1).strip()
        if c:
            return c
    bt = re.search(r"`([^`]+)`", text)
    if bt:
        c = bt.group(1).strip()
        if c:
            return c
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "//", "-", "*", "Here", "The", "This", "Note")):
            if any(ch in s for ch in r"\.+*?[]{}()|^$"):
                return s
    return text.strip() or None


def _extract_rule_json(text: str) -> Optional[dict]:
    """
    Extract and validate the structured rule JSON from LLM response.
    Returns a dict with keys: pattern, flags, description, placeholder, weight, examples.
    Returns None if parsing fails (caller should fall back to legacy extraction).
    """
    import json
    # Try fenced ```json ... ``` block first
    fenced = re.search(r"```(?:json)?\s*\n?({.*?})\s*```", text, re.DOTALL)
    raw_json = fenced.group(1).strip() if fenced else None

    # Fallback: find the first {...} blob in the text
    if not raw_json:
        m = re.search(r"({[\s\S]*})", text)
        raw_json = m.group(1).strip() if m else None

    if not raw_json:
        return None

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return None

    # Validate required fields
    if not isinstance(data.get("pattern"), str) or not data["pattern"].strip():
        return None

    # Normalise / supply defaults for optional fields
    try:
        weight = max(1, min(10, int(float(data.get("weight", 5)))))
    except (TypeError, ValueError):
        weight = 5
    result = {
        "pattern": data["pattern"].strip(),
        "flags": str(data.get("flags") or "").strip(),
        "description": str(data.get("description") or "").strip() or None,
        "placeholder": str(data.get("placeholder") or "[MASKED]").strip(),
        "weight": weight,
        "examples": None,
    }

    raw_ex = data.get("examples")
    if isinstance(raw_ex, dict):
        match_ex = raw_ex.get("match") or []
        no_match_ex = raw_ex.get("no_match") or []
        result["examples"] = {
            "match": [str(x) for x in match_ex[:5]],
            "no_match": [str(x) for x in no_match_ex[:3]],
        }

    return result


# keyword → category mapping (checked in order; first match wins)
_CATEGORY_KEYWORDS: List[tuple[str, str]] = [
    (r"email|e-mail", "PII"),
    (r"phone|mobile|telephone|fax", "PII"),
    (r"name|surname|first.?name|last.?name|full.?name", "PII"),
    (r"address|postcode|zip.?code|postal", "PII"),
    (r"ssn|social.?security|national.?id|passport|birth.?date|dob", "PII"),
    (r"credit.?card|debit.?card|card.?number|cvv|cvc", "Finance"),
    (r"iban|bank|account.?number|routing|swift|bic", "Finance"),
    (r"salary|tax|invoice|vat|payment", "Finance"),
    (r"medical|health|diagnosis|prescription|patient|clinical|icd", "Health"),
    (r"password|passwd|secret|token|api.?key|credential|auth|bearer", "Credential"),
    (r"ip.?address|ipv4|ipv6|mac.?address|cidr", "Network"),
    (r"url|domain|hostname|uri|endpoint", "Network"),
    (r"uuid|guid", "Identifier"),
    (r"date|time|timestamp|datetime", "DateTime"),
]


def _suggest_meta(description: str) -> tuple[str, str]:
    """Return (suggested_name, suggested_category) from a free-text description."""
    desc_lower = description.lower()
    category = "Custom"
    for pattern_str, cat in _CATEGORY_KEYWORDS:
        if re.search(pattern_str, desc_lower):
            category = cat
            break

    # Build name: capitalise description, truncate, append "Pattern"
    clean = re.sub(r"\s+", " ", description.strip())
    if len(clean) > 40:
        clean = clean[:37].rstrip() + "..."
    name = clean[0].upper() + clean[1:] if clean else "AI Generated"
    name = name + " Pattern" if not name.lower().endswith("pattern") else name

    return name, category


# ---- Provider abstraction ---------------------------------------------------

class LlmBackend(ABC):
    """Abstract interface every LLM provider must implement."""

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def metadata(self) -> Dict[str, Any]: ...

    @abstractmethod
    async def generate(self, model: str, user_prompt: str) -> str:
        """Return raw LLM response text (raises ConnectionError / RuntimeError on failure)."""
        ...


class OllamaBackend(LlmBackend):
    """Ollama local server - /api/generate."""

    provider_id = "ollama"

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "id": "ollama",
            "name": "Ollama",
            "kind": "ollama",
            "base_url": OLLAMA_BASE_URL,
            "default_model": OLLAMA_DEFAULT_MODEL,
            "supports_model_list": True,
            "note": "Local Ollama server",
        }

    async def generate(self, model: str, user_prompt: str) -> str:
        payload = {
            "model": model,
            "prompt": user_prompt,
            "system": _SYSTEM_PROMPT,
            "stream": False,
            "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 512},
        }
        url = f"{OLLAMA_BASE_URL}/api/generate"
        logger.debug("ollama_request url=%s model=%s prompt_len=%d", url, model, len(user_prompt))
        try:
            resp = await get_http_client().post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot reach Ollama at {OLLAMA_BASE_URL}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Ollama HTTP {exc.response.status_code}: {exc.response.text}") from exc

        raw = data.get("response", "").strip()
        logger.debug("ollama_response model=%s response_len=%d", model, len(raw))
        return raw

    async def list_models(self) -> List[Dict[str, Any]]:
        url = f"{OLLAMA_BASE_URL}/api/tags"
        logger.debug("ollama_list_models url=%s", url)
        try:
            resp = await get_http_client().get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot reach Ollama at {OLLAMA_BASE_URL}: {exc}") from exc
        models = data.get("models", [])
        logger.debug("ollama_list_models found=%d", len(models))
        return models


class OpenAICompatBackend(LlmBackend):
    """OpenAI Chat Completions-compatible endpoint (OpenCode, LocalAI, etc.)."""

    provider_id = "opencode"

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "id": "opencode",
            "name": "OpenCode (oc)",
            "kind": "openai_compat",
            "base_url": OPENCODE_BASE_URL,
            "default_model": OPENCODE_DEFAULT_MODEL,
            "supports_model_list": False,
            "note": "Local OpenCode HTTP service (OpenAI-compatible)",
        }

    async def generate(self, model: str, user_prompt: str) -> str:
        url = f"{OPENCODE_BASE_URL}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 512,
        }
        headers: Dict[str, str] = {}
        if OPENCODE_API_KEY:
            headers["Authorization"] = f"Bearer {OPENCODE_API_KEY}"

        logger.debug("opencode_request url=%s model=%s prompt_len=%d", url, model, len(user_prompt))
        try:
            resp = await get_http_client().post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(f"Cannot reach OpenCode at {OPENCODE_BASE_URL}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"OpenCode HTTP {exc.response.status_code}: {exc.response.text}") from exc

        try:
            raw = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected OpenCode response structure: {data}") from exc

        logger.debug("opencode_response model=%s response_len=%d", model, len(raw))
        return raw


# ---- Provider registry ------------------------------------------------------

_ollama = OllamaBackend()
_opencode = OpenAICompatBackend()

# To add a new provider: create a LlmBackend subclass and register it here.
_REGISTRY: Dict[str, LlmBackend] = {
    _ollama.provider_id: _ollama,
    _opencode.provider_id: _opencode,
}

_PROVIDERS_ORDERED: List[LlmBackend] = [_ollama, _opencode]


# ---- Request / Response models ----------------------------------------------

class GenerateRegexRequest(BaseModel):
    description: str = Field(..., min_length=5, max_length=2000)
    model: str = Field(..., min_length=1, max_length=128)
    context: Optional[str] = Field(default=None, max_length=500)
    provider: Optional[Literal["ollama", "opencode"]] = Field(
        default=None,
        description="Provider id: 'ollama' or 'opencode'. Defaults to 'ollama'.",
    )


class GenerateRegexResponse(BaseModel):
    # Core rule fields — ready to POST directly to /rules
    pattern: str
    flags: str = ""
    description: Optional[str] = None
    placeholder: str = "[MASKED]"
    weight: int = 5
    examples: Optional[Dict[str, List[str]]] = None
    # Metadata
    model: str
    provider: str
    suggested_name: Optional[str] = None
    suggested_category: Optional[str] = None
    # Raw LLM output for debugging
    raw_response: str
    # True if structured JSON was successfully parsed; False = legacy fallback
    structured: bool = False


# ---- Endpoints --------------------------------------------------------------

@router.get("/llm/models", summary="List available local Ollama models")
async def list_models():
    """Return locally installed Ollama models."""
    try:
        models = await _ollama.list_models()
    except ConnectionError as exc:
        logger.warning("list_models: Ollama unreachable - %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "ollama_url": OLLAMA_BASE_URL,
        "total": len(models),
        "models": [
            {
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "modified_at": m.get("modified_at", ""),
                "details": m.get("details", {}),
            }
            for m in models
        ],
    }


@router.get("/llm/providers", summary="List supported local LLM providers")
async def list_providers():
    """Return the list of supported local LLM providers."""
    providers = [b.metadata for b in _PROVIDERS_ORDERED]
    return {"total": len(providers), "providers": providers}


@router.post("/llm/generate-regex", summary="Generate a regex pattern using local LLM")
async def generate_regex(body: GenerateRegexRequest):
    """
    Generate a regex pattern from a natural language description.

    Dispatches via the provider registry (no branching on provider type).
    Structured logs carry request_id, provider, model, elapsed time, and
    desc_len to make tracing and debugging straightforward.
    """
    request_id = str(uuid.uuid4())[:8]
    provider_id = body.provider or "ollama"

    backend = _REGISTRY.get(provider_id)
    if backend is None:
        logger.warning(
            "generate_regex: unknown provider request_id=%s provider=%s",
            request_id, provider_id,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider_id}'. Valid options: {list(_REGISTRY.keys())}",
        )

    user_prompt = _build_user_prompt(body.description, body.context)

    logger.info(
        "generate_regex_start request_id=%s provider=%s model=%s desc_len=%d context=%s",
        request_id, provider_id, body.model, len(body.description),
        "yes" if body.context else "no",
    )
    t0 = time.monotonic()

    try:
        raw_text = await backend.generate(body.model, user_prompt)
    except ConnectionError as exc:
        elapsed = time.monotonic() - t0
        logger.error(
            "generate_regex_connection_error request_id=%s provider=%s model=%s"
            " elapsed=%.2fs error=%s",
            request_id, provider_id, body.model, elapsed, exc,
        )
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        elapsed = time.monotonic() - t0
        logger.error(
            "generate_regex_runtime_error request_id=%s provider=%s model=%s"
            " elapsed=%.2fs error=%s",
            request_id, provider_id, body.model, elapsed, exc,
        )
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.exception(
            "generate_regex_unexpected_error request_id=%s provider=%s model=%s elapsed=%.2fs",
            request_id, provider_id, body.model, elapsed,
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}")

    elapsed = time.monotonic() - t0

    if not raw_text:
        logger.warning(
            "generate_regex_empty_response request_id=%s provider=%s model=%s elapsed=%.2fs",
            request_id, provider_id, body.model, elapsed,
        )
        raise HTTPException(status_code=502, detail="LLM returned an empty response")

    suggested_name, suggested_category = _suggest_meta(body.description)

    # Try structured JSON extraction first; fall back to legacy pattern-only extraction
    rule_json = _extract_rule_json(raw_text)
    if rule_json:
        return GenerateRegexResponse(
            pattern=rule_json["pattern"],
            flags=rule_json["flags"],
            description=rule_json["description"],
            placeholder=rule_json["placeholder"],
            weight=min(10, max(1, rule_json["weight"])),
            examples=rule_json["examples"],
            model=body.model,
            provider=provider_id,
            suggested_name=suggested_name,
            suggested_category=suggested_category,
            raw_response=raw_text,
            structured=True,
        )

    # Legacy fallback: LLM didn't return valid JSON
    pattern = _extract_regex(raw_text)
    if not pattern:
        logger.warning(
            "generate_regex_no_pattern request_id=%s provider=%s model=%s"
            " elapsed=%.2fs raw_preview=%.80r",
            request_id, provider_id, body.model, elapsed, raw_text,
        )
        raise HTTPException(status_code=502, detail="Could not extract a regex from the LLM response")

    logger.info(
        "generate_regex_ok request_id=%s provider=%s model=%s elapsed=%.2fs pattern_len=%d (legacy fallback)",
        request_id, provider_id, body.model, elapsed, len(pattern),
    )

    return GenerateRegexResponse(
        pattern=pattern,
        model=body.model,
        provider=provider_id,
        raw_response=raw_text,
        suggested_name=suggested_name,
        suggested_category=suggested_category,
        structured=False,
    )
