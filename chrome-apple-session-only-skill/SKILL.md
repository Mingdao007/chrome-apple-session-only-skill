---
name: chrome-apple-session-only-skill
description: |
  Use when Apple login in Google Chrome becomes unreliable because old cookies or
  stale site data keep polluting the flow. Audits or applies Apple-specific
  session-only cookie rules for Google Chrome on Ubuntu or macOS.
---

# Chrome Apple Session-Only Cleanup

## Overview

Use this skill when the user wants a selected Google Chrome login surface to start
clean on the next browser launch rather than reusing stale site state.

Keep Apple as the only supported path.

Do not frame this as "permanently block Apple cookies." The intended behavior is:

- the target login can work during the current Chrome session
- once all Chrome windows fully exit, target session data should be treated as disposable
- the next Chrome launch should start from a cleaner target state

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
python3 scripts/chrome_apple_session_only.py audit --target apple --profile "Profile 2"
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
   - open the Apple login once and test it
   - fully close Chrome
   - reopen Chrome and verify the Apple login starts clean again

## Rules

- Treat `audit` as the default first step.
- `apply` must not run while Google Chrome is still open.
- Keep the supported scope fixed to `apple.com`, `[*.]apple.com`, and `appleid.apple.com`.
- Do not silently widen scope beyond that Apple family.
- Keep the cleanup strategy conservative:
  - write Apple cookie rules as `session_only`
  - delete stale Apple cookie rows
  - remove Apple site-state metadata that is directly addressable
  - remove directly identifiable Apple-origin storage artifacts only when the on-disk path safely encodes the host
- Do not claim that every opaque Chrome LevelDB record is surgically scrubbed.
- On macOS, if the user asks whether the workflow is already personally validated on your machine, state that Apple `audit`, `apply --dry-run`, and `apply` were live-validated on a real Mac on 2026-04-09 against a `Default` profile.
- If the user asks whether the post-relaunch interactive Apple login flow itself was fully verified, state that this remains a manual operator follow-up step because it depends on the user's own account flow.

## Reference

For exact supported paths, rule shapes, cleanup boundaries, and script behavior,
see [references/platform-paths-and-safety.md](references/platform-paths-and-safety.md).
