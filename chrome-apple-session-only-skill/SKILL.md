---
name: chrome-apple-session-only-skill
description: |
  Use when Apple login in Google Chrome becomes unreliable because old Apple cookies
  or stale site data keep polluting the flow. Audits or applies Apple session-only
  cookie rules for Google Chrome on Ubuntu or macOS, targeting apple.com,
  [*.]apple.com, and appleid.apple.com.
---

# Chrome Apple Session-Only Cleanup

## Overview

Use this skill when the user wants Apple login in Google Chrome to start clean on
the next browser launch rather than reusing stale Apple state.

Do not frame this as "permanently block Apple cookies." The intended behavior is:

- Apple login can work during the current Chrome session
- once all Chrome windows fully exit, Apple session data should be treated as disposable
- the next Chrome launch should start from a cleaner Apple state

This skill supports Google Chrome on:

- Ubuntu: `~/.config/google-chrome`
- macOS: `~/Library/Application Support/Google/Chrome`

Prefer the helper script for deterministic changes.

## Quick Start

Audit first:

```bash
python3 scripts/chrome_apple_session_only.py audit
```

Preview mutations:

```bash
python3 scripts/chrome_apple_session_only.py apply --dry-run
```

Apply for real:

```bash
python3 scripts/chrome_apple_session_only.py apply
```

Override the Chrome profile if needed:

```bash
python3 scripts/chrome_apple_session_only.py audit --profile "Profile 2"
```

## Workflow

1. Run `audit` first and read:
   - detected Chrome root
   - chosen profile
   - whether Chrome appears to be running
   - whether Apple `session_only` rules are already present
   - current Apple cookie counts
   - current Apple metadata/artifact hits
2. If the user wants changes, make sure all Chrome windows are closed.
3. Run `apply --dry-run` if the user wants a no-write preview.
4. Run `apply` only after confirming Chrome is closed.
5. After apply, tell the user to:
   - open Apple login once and test it
   - fully close Chrome
   - reopen Chrome and verify Apple starts clean again

## Rules

- Treat `audit` as the default first step.
- `apply` must not run while Google Chrome is still open.
- Keep the supported domain scope fixed in v1:
  - `apple.com`
  - `[*.]apple.com`
  - `appleid.apple.com`
- Do not silently widen scope to `icloud.com`.
- Keep the cleanup strategy conservative:
  - write Apple cookie rules as `session_only`
  - delete stale Apple cookie rows
  - remove Apple site-state metadata that is directly addressable
  - remove directly identifiable Apple-origin storage artifacts only when the on-disk path safely encodes the Apple host
- Do not claim that every opaque Chrome LevelDB record is surgically scrubbed.
- On macOS, if the user asks whether the workflow is already personally validated on your machine, state that the path is implemented but public validation may still be pending until the latest real-machine check is done.

## Reference

For exact supported paths, rule shapes, cleanup boundaries, and script behavior,
see [references/platform-paths-and-safety.md](references/platform-paths-and-safety.md).

