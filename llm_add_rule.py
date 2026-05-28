#!/usr/bin/env python3
"""
llm_add_rule.py — Generate a masking regex via LLM and submit for approval (or create directly).

Default behaviour: generates pattern + submits as a SUGGESTION (pending admin/org-owner approval).
Use --create to bypass the approval queue and create the rule immediately.

Usage:
  # Generate + submit for approval (default)
  python llm_add_rule.py -k <api_key> -d "SUSE registration code like Regcode-XXXXX"

  # Add a reason for the reviewer
  python llm_add_rule.py -k <api_key> -d "AWS S3 bucket URL" --reason "Found in audit logs"

  # Create immediately (skip approval queue) — requires admin or org-owner key
  python llm_add_rule.py -k <api_key> -d "IPv6 address" --scope org --create

  # Preview payload without sending anything
  python llm_add_rule.py -k <api_key> -d "SUSE reg code" --dry-run

Options:
  -k / --key        API key (required)
  -d / --desc       Natural language description of what to mask (required)
  -c / --context    Extra context hint for the LLM (optional)
  -r / --reason     Reason for the suggestion shown to reviewer (default: auto-generated)
  -s / --server     Server base URL (default: http://10.146.15.188:8080)
  -m / --model      LLM model name (default: qwen2.5-coder:7b)
  -p / --provider   LLM provider: ollama | opencode (default: ollama)
  --scope           Rule scope: system | org | private (default: private)
  --strategy        Mask strategy: asterisk | placeholder | partial | hash (default: placeholder)
  --create          Create rule directly (skip approval queue)
  --dry-run         Show final payload without sending any request
  --name            Override the suggested rule name
  --category        Override the suggested category
"""

import argparse
import json
import sys
import urllib.error
import urllib.request


BASE = "/api/v1"


def request(server: str, method: str, path: str, key: str, body=None):
    url = server.rstrip("/") + BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {
        "X-API-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        print(f"\n[HTTP {e.code}] {url}", file=sys.stderr)
        try:
            err = json.loads(body_text)
            print(json.dumps(err, indent=2, ensure_ascii=False), file=sys.stderr)
        except Exception:
            print(body_text, file=sys.stderr)
        sys.exit(1)


def color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def print_generated(resp: dict):
    ok = resp.get("structured", False)
    print(f"\n{'='*60}")
    print(color("  LLM GENERATED RULE", "1;36"))
    print(f"{'='*60}")
    print(f"  Pattern   : {color(resp['pattern'], '1;33')}")
    print(f"  Flags     : {resp.get('flags') or '(none)'}")
    print(f"  Placeholder: {resp.get('placeholder', '[MASKED]')}")
    print(f"  Weight    : {resp.get('weight', 5)}/10")
    print(f"  Description: {resp.get('description') or '(none)'}")
    print(f"  Suggested name    : {resp.get('suggested_name')}")
    print(f"  Suggested category: {resp.get('suggested_category')}")
    print(f"  Structured JSON   : {'✓' if ok else '✗ (legacy fallback)'}")

    examples = resp.get("examples")
    if examples:
        print(f"\n  Examples that MATCH:")
        for ex in examples.get("match", []):
            print(f"    + {ex}")
        print(f"  Examples that DO NOT match:")
        for ex in examples.get("no_match", []):
            print(f"    - {ex}")
    print()


def build_rule_payload(resp: dict, args: argparse.Namespace) -> dict:
    name = args.name or resp.get("suggested_name") or "AI Generated Rule"
    category = args.category or resp.get("suggested_category") or "Custom"
    return {
        "name": name,
        "category": category,
        "pattern": resp["pattern"],
        "flags": resp.get("flags") or "",
        "strategy": args.strategy,
        "placeholder": resp.get("placeholder") or "[MASKED]",
        "weight": resp.get("weight") or 5,
        "enabled": True,
        "scope": args.scope,
        "description": resp.get("description"),
        "example": None,
    }


def build_suggestion_payload(resp: dict, args: argparse.Namespace) -> dict:
    name = args.name or resp.get("suggested_name") or "AI Generated Rule"
    category = args.category or resp.get("suggested_category") or "Custom"
    reason = args.reason or (
        f"AI-generated via LLM ({args.provider}/{args.model}). "
        f"Description: {args.desc}"
    )
    return {
        "action": "create",
        "rule_id": None,
        "name": name,
        "category": category,
        "pattern": resp["pattern"],
        "flags": resp.get("flags") or "",
        "strategy": args.strategy,
        "placeholder": resp.get("placeholder") or "[MASKED]",
        "weight": resp.get("weight") or 5,
        "reason": reason,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate masking regex via LLM; submit for approval (default) or create directly.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-k", "--key", required=True, help="API key")
    parser.add_argument("-d", "--desc", required=True, help="What to mask (natural language)")
    parser.add_argument("-c", "--context", default=None, help="Extra hint for LLM")
    parser.add_argument("-r", "--reason", default=None, help="Reason shown to reviewer")
    parser.add_argument("-s", "--server", default="http://10.146.15.188:8080")
    parser.add_argument("-m", "--model", default="qwen2.5-coder:7b")
    parser.add_argument("-p", "--provider", default="ollama", choices=["ollama", "opencode"])
    parser.add_argument("--scope", default="private", choices=["system", "org", "private"])
    parser.add_argument("--strategy", default="placeholder",
                        choices=["asterisk", "placeholder", "partial", "hash"])
    parser.add_argument("--create", action="store_true",
                        help="Create rule directly (skip approval queue)")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending")
    parser.add_argument("--name", default=None, help="Override rule name")
    parser.add_argument("--category", default=None, help="Override rule category")
    args = parser.parse_args()

    # ── Step 1: Generate ────────────────────────────────────────────────────
    total_steps = 2
    print(f"[1/{total_steps}] Asking LLM ({args.provider}/{args.model}) to generate regex...")
    print(f"      Description: {color(args.desc, '1')}")
    if args.context:
        print(f"      Context: {args.context}")

    generate_payload = {
        "description": args.desc,
        "model": args.model,
        "provider": args.provider,
    }
    if args.context:
        generate_payload["context"] = args.context

    resp = request(args.server, "POST", "/llm/generate-regex", args.key, generate_payload)
    print_generated(resp)

    # ── Step 2: Submit suggestion or create directly ─────────────────────────
    if args.create:
        # ── Direct creation ─────────────────────────────────────────────────
        rule_payload = build_rule_payload(resp, args)
        if args.dry_run:
            print(color("[DRY RUN] POST /rules payload:", "1;35"))
            print(json.dumps(rule_payload, indent=2, ensure_ascii=False))
            return
        print(f"[2/{total_steps}] Creating rule directly (scope={args.scope})...")
        result = request(args.server, "POST", "/rules", args.key, rule_payload)
        created = result.get("rule", {})
        print(color(f"  ✓ Rule created: id={created.get('id')}  name=\"{created.get('name')}\"", "1;32"))
        print(f"  scope={created.get('scope')}  category={created.get('category')}  weight={created.get('weight')}")
    else:
        # ── Submit for approval (default) ────────────────────────────────────
        suggestion_payload = build_suggestion_payload(resp, args)
        if args.dry_run:
            print(color("[DRY RUN] POST /rules/suggestions payload:", "1;35"))
            print(json.dumps(suggestion_payload, indent=2, ensure_ascii=False))
            return
        print(f"[2/{total_steps}] Submitting suggestion for approval...")
        result = request(args.server, "POST", "/rules/suggestions", args.key, suggestion_payload)
        s = result.get("suggestion", {})
        print(color(f"  ✓ Suggestion #{s.get('id')} submitted — status: {s.get('status', 'pending')}", "1;32"))
        print(f"  name=\"{s.get('name')}\"  pattern={s.get('pattern')}")
        print(f"  Awaiting review by admin or org owner.")


if __name__ == "__main__":
    main()
