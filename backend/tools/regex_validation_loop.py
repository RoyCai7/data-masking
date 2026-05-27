#!/usr/bin/env python3
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Tuple


def call_ollama(base_url: str, model: str, prompt: str, timeout: int = 60) -> Tuple[str, Dict]:
    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "stream": False,
        "prompt": prompt,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    response = data.get("response", "")
    return response, data


def normalize_regex(text: str) -> str:
    value = text.strip()
    value = value.replace("```regex", "").replace("```", "").strip()

    if value.startswith(("r\"", "r'")) and value.endswith(("\"", "'")):
        value = value[2:-1]
    elif (value.startswith("\"") and value.endswith("\"")) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]

    return value.strip()


def evaluate_regex(pattern: str, spec: Dict, mode: str = "fullmatch") -> Tuple[bool, List[str]]:
    failures: List[str] = []

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return False, [f"compile_error: {exc}"]

    matcher = compiled.fullmatch if mode == "fullmatch" else compiled.search

    for value in spec.get("should_match", []):
        if matcher(value) is None:
            failures.append(f"should_match_failed: {value}")

    for value in spec.get("should_not_match", []):
        if matcher(value) is not None:
            failures.append(f"should_not_match_failed: {value}")

    return len(failures) == 0, failures


def build_prompt(spec: Dict, prior_regex: str = "", failures: List[str] = None) -> str:
    failures = failures or []

    lines = [
        "Return ONLY one regex pattern. No markdown, no explanation, no code block.",
        f"Task: {spec['description']}",
        "Constraints:",
        "- Use anchors ^ and $ when appropriate.",
        "- Output exactly one line containing only the regex.",
        "",
        "MUST MATCH:",
    ]
    for item in spec.get("should_match", []):
        lines.append(f"- {item}")

    lines.append("")
    lines.append("MUST NOT MATCH:")
    for item in spec.get("should_not_match", []):
        lines.append(f"- {item}")

    if prior_regex:
        lines.append("")
        lines.append(f"Previous regex failed: {prior_regex}")
    if failures:
        lines.append("Failure reasons:")
        for fail in failures:
            lines.append(f"- {fail}")
        lines.append("Please fix these errors.")

    return "\n".join(lines)


def load_spec(args: argparse.Namespace) -> Dict:
    if args.spec_file:
        with open(args.spec_file, "r", encoding="utf-8") as f:
            return json.load(f)
    if args.spec_json:
        return json.loads(args.spec_json)

    raise ValueError("Provide --spec-file or --spec-json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate regex with Ollama and validate in a retry loop"
    )
    parser.add_argument("--model", required=True, help="Ollama model name")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:11434",
        help="Ollama API base URL, e.g. http://127.0.0.1:11434 or tunneled http://127.0.0.1:18080",
    )
    parser.add_argument("--spec-file", help="Path to JSON spec file")
    parser.add_argument("--spec-json", help="Inline JSON spec string")
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--match-mode", choices=["fullmatch", "search"], default="fullmatch")
    parser.add_argument(
        "--fallback-regex",
        default="",
        help="Fallback regex to use if all attempts fail",
    )
    parser.add_argument("--timeout", type=int, default=60)

    args = parser.parse_args()

    try:
        spec = load_spec(args)
    except Exception as exc:
        print(f"ERROR: failed to load spec: {exc}", file=sys.stderr)
        return 2

    if "description" not in spec:
        print("ERROR: spec must include 'description'", file=sys.stderr)
        return 2

    failures: List[str] = []
    previous_regex = ""

    for attempt in range(1, args.max_attempts + 1):
        prompt = build_prompt(spec, previous_regex, failures)
        try:
            raw_response, meta = call_ollama(args.base_url, args.model, prompt, timeout=args.timeout)
        except urllib.error.URLError as exc:
            print(f"ERROR: request failed on attempt {attempt}: {exc}", file=sys.stderr)
            return 3

        regex_pattern = normalize_regex(raw_response)
        is_valid, failures = evaluate_regex(regex_pattern, spec, mode=args.match_mode)

        eval_count = meta.get("eval_count", 0)
        eval_duration = meta.get("eval_duration", 0)
        rate = 0.0
        if eval_duration:
            rate = eval_count / (eval_duration / 1e9)

        print(f"attempt={attempt} regex={regex_pattern}")
        print(f"metrics: eval_count={eval_count} eval_rate={rate:.1f}t/s")

        if is_valid:
            print("status=PASS")
            print(json.dumps({"regex": regex_pattern, "status": "PASS"}, ensure_ascii=False))
            return 0

        print("status=FAIL")
        for fail in failures:
            print(f"  - {fail}")

        previous_regex = regex_pattern

    if args.fallback_regex:
        fallback_ok, fallback_failures = evaluate_regex(args.fallback_regex, spec, mode=args.match_mode)
        if fallback_ok:
            print("status=FALLBACK_PASS")
            print(json.dumps({"regex": args.fallback_regex, "status": "FALLBACK_PASS"}, ensure_ascii=False))
            return 0

        print("status=FALLBACK_FAIL")
        for fail in fallback_failures:
            print(f"  - {fail}")

    print("status=FINAL_FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
