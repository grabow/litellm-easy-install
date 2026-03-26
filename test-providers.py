#!/usr/bin/env python3
"""
HSOG LiteLLM Provider Test Suite
===================================
Testet jeden Provider mit einem multi-turn Tool-Call, genauso wie Codex es macht:

  Turn 1: User stellt Frage → Modell antwortet mit tool_call
  Turn 2: Tool-Ergebnis wird gesendet → Modell gibt finale Antwort

Aufruf:
    python3 test-providers.py
    python3 test-providers.py --url http://localhost:4000
"""

import argparse
import json
import os
import sys
import time
import requests

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

PROVIDERS = ["academic", "nvidia", "openrouter"]

# Tool-Definitionen (wie Codex sie schickt)
SHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "shell_execute",
        "description": "Execute a shell command and return the output.",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command and arguments, e.g. [\"ls\", \"-la\"]"
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory for the command"
                }
            },
            "required": ["cmd"],
            "additionalProperties": False
        }
    }
}

APPLY_PATCH_TOOL = {
    "type": "function",
    "function": {
        "name": "apply_patch",
        "description": (
            "Use the `apply_patch` tool to edit files.\n"
            "Your patch language is a stripped-down, file-oriented diff format.\n\n"
            "*** Begin Patch\n"
            "[ one or more file sections ]\n"
            "*** End Patch\n\n"
            "Each file section starts with one of:\n"
            "  *** Add File: <path>     — create a new file (lines prefixed with +)\n"
            "  *** Delete File: <path>  — remove a file\n"
            "  *** Update File: <path>  — patch an existing file\n\n"
            "Pass the complete patch text as the `input` parameter."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "The entire contents of the apply_patch command"
                }
            },
            "required": ["input"],
            "additionalProperties": False
        }
    }
}

TOOLS = [SHELL_TOOL, APPLY_PATCH_TOOL]

# Simuliertes Tool-Ergebnis für shell_execute
FAKE_LS_OUTPUT = json.dumps({
    "stdout": "codex-hsog\nconfig.toml\nstart.sh\nREADME.md",
    "stderr": "",
    "exit_code": 0
})

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def read_dotenv(path: str) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def chat(url: str, key: str, model: str, messages: list, tools: list | None = None,
         stream: bool = False) -> dict:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    r = requests.post(
        f"{url}/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=180,
    )
    r.raise_for_status()
    return r.json()


def models(url: str, key: str) -> list:
    headers = {"Authorization": f"Bearer {key}"}
    r = requests.get(f"{url}/v1/models", headers=headers, timeout=10)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


# ---------------------------------------------------------------------------
# Test-Szenarien
# ---------------------------------------------------------------------------

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


def test_connectivity(url: str, key: str, provider: str) -> tuple[bool, str]:
    """Prüft ob der Provider im LiteLLM-Modell-Katalog vorhanden ist."""
    available = models(url, key)
    if provider in available:
        return True, f"found in model list ({len(available)} models total)"
    return False, f"NOT found. Available: {available}"


def test_text_only(url: str, key: str, provider: str) -> tuple[bool, str]:
    """Einfacher Single-Turn ohne Tools."""
    msgs = [{"role": "user", "content": "Reply with exactly one word: OK"}]
    resp = chat(url, key, provider, msgs)
    content = resp["choices"][0]["message"].get("content") or ""
    ok = bool(content.strip())
    return ok, f"response={content.strip()[:80]!r}"


def test_tool_call(url: str, key: str, provider: str) -> tuple[bool, str]:
    """
    Multi-Turn Tool-Call Test (entspricht dem Bug-Szenario):

      Turn 1: Modell soll shell_execute aufrufen
      Turn 2: Tool-Ergebnis zurücksenden, Modell gibt finale Antwort

    Genau dieser Weg war wegen des doppelten /v1 gebrochen.
    """
    # Turn 1
    msgs = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Use the shell_execute tool to answer questions about the filesystem.",
        },
        {
            "role": "user",
            "content": "List the files in the current directory using the shell_execute tool.",
        },
    ]
    resp1 = chat(url, key, provider, msgs, tools=TOOLS)
    msg1 = resp1["choices"][0]["message"]

    tool_calls = msg1.get("tool_calls") or []
    if not tool_calls:
        content = (msg1.get("content") or "")
        return False, f"TURN 1: model did not emit a tool_call. content={content[:120]!r}"

    tc = tool_calls[0]
    fn_obj = tc.get("function") or {}
    fn_name = fn_obj.get("name", "?")
    fn_args_raw = fn_obj.get("arguments", "{}")
    try:
        fn_args = json.loads(fn_args_raw)
    except json.JSONDecodeError:
        fn_args = fn_args_raw

    # Turn 2: Tool-Ergebnis + finale Antwort
    msgs.append(msg1)  # assistant message with tool_call
    msgs.append({
        "role": "tool",
        "tool_call_id": tc["id"],
        "content": FAKE_LS_OUTPUT,
    })
    resp2 = chat(url, key, provider, msgs, tools=TOOLS)
    msg2 = resp2["choices"][0]["message"]
    final = msg2.get("content") or ""
    tool_calls2 = msg2.get("tool_calls") or []

    if tool_calls2:
        # Model made a second tool call – still counts as working tool-call support
        tc2 = tool_calls2[0]
        detail = (
            f"TURN 1: tool={fn_name}, args={fn_args!r:.80}  |  "
            f"TURN 2: second tool_call={tc2['function']['name']} (OK)"
        )
        return True, detail

    ok = bool(final.strip())
    detail = (
        f"TURN 1: tool={fn_name}, args={fn_args!r:.80}  |  "
        f"TURN 2: final={final.strip()[:100]!r}"
    )
    return ok, detail


# ---------------------------------------------------------------------------
# Haupt-Testlauf
# ---------------------------------------------------------------------------

TESTS = [
    ("connectivity",  test_connectivity),
    ("text-only",     test_text_only),
    ("tool-call (multi-turn)", test_tool_call),
]


def run_all(url: str, key: str, providers: list[str]) -> int:
    failures = 0
    width = max(len(p) for p in providers)

    print(f"\nLiteLLM URL: {url}")
    print("=" * 72)

    for provider in providers:
        print(f"\n{'─' * 72}")
        print(f"  Provider: {provider}")
        print(f"{'─' * 72}")

        for test_name, test_fn in TESTS:
            label = f"  {test_name:<30}"
            try:
                t0 = time.monotonic()
                ok, detail = test_fn(url, key, provider)
                elapsed = time.monotonic() - t0
                icon = PASS if ok else FAIL
                if not ok:
                    failures += 1
                print(f"{label} {icon}  ({elapsed:.1f}s)  {detail}")
            except requests.HTTPError as e:
                failures += 1
                print(f"{label} {FAIL}  HTTP {e.response.status_code}: {e.response.text[:200]}")
            except Exception as e:
                failures += 1
                print(f"{label} {FAIL}  {type(e).__name__}: {e}")

    print(f"\n{'=' * 72}")
    if failures == 0:
        print(f"{PASS}  All tests passed.")
    else:
        print(f"{FAIL}  {failures} test(s) failed.")
    print()
    return failures


def main():
    parser = argparse.ArgumentParser(description="HSOG LiteLLM provider test suite")
    parser.add_argument("--url", default=os.environ.get("LITELLM_URL", "http://localhost:4000"),
                        help="LiteLLM base URL (default: http://localhost:4000)")
    parser.add_argument("--providers", nargs="+", default=PROVIDERS,
                        help=f"Providers to test (default: {PROVIDERS})")
    parser.add_argument("--env", default=os.path.join(os.path.dirname(__file__), ".env"),
                        help="Path to .env file")
    args = parser.parse_args()

    env = read_dotenv(args.env)
    key = env.get("LITELLM_MASTER_KEY") or os.environ.get("LITELLM_MASTER_KEY")
    if not key:
        print("ERROR: LITELLM_MASTER_KEY not found in .env or environment.", file=sys.stderr)
        sys.exit(1)

    failures = run_all(args.url, key, args.providers)
    sys.exit(min(failures, 1))


if __name__ == "__main__":
    main()
