# chrome-apple-session-only-skill

A Codex skill for making Apple login in Google Chrome start clean on the next browser launch by enforcing Apple `session_only` cookie rules and clearing stale Apple login data.

Chinese mirror: [README.zh-CN.md](README.zh-CN.md)

## Validated Baseline

| Component | Status |
|-----------|--------|
| Ubuntu | Live-validated |
| macOS | Live-validated on a real Mac on 2026-04-09 |
| Google Chrome on Ubuntu | 146.0.7680.164 |
| Google Chrome on macOS | 146.0.7680.178 |
| Chrome profile model | `Local State` + per-profile `Preferences` + `Cookies` |
| Validated macOS profile shape | single `Default` profile resolved from `Local State` |
| Domain scope | `apple.com`, `[*.]apple.com`, `appleid.apple.com` |

## Problems Covered

- Apple login in Chrome gets polluted by old Apple cookies or site data
- Apple login works once, then later login attempts become unreliable or oddly sticky
- You want Apple data to survive only for the current Chrome session and disappear after Chrome fully exits
- You want an audit-first workflow before mutating a Chrome profile

## What Ships

- `chrome-apple-session-only-skill/`: installable Codex skill package
- `chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py`: audit/apply helper for Ubuntu and macOS Google Chrome profiles
- `chrome-apple-session-only-skill/agents/openai.yaml`: Codex metadata
- `tests/test_chrome_apple_session_only.py`: stdlib unit tests for synthetic Chrome profile trees

## Install

1. Copy `chrome-apple-session-only-skill/` into `${CODEX_HOME:-$HOME/.codex}/skills/`.
2. Restart Codex or refresh local skills.
3. Invoke the skill as `$chrome-apple-session-only-skill`.

## Script Usage

Audit only:

```bash
python3 chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py audit
```

Dry-run apply:

```bash
python3 chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py apply --dry-run
```

Apply to a specific Chrome profile:

```bash
python3 chrome-apple-session-only-skill/scripts/chrome_apple_session_only.py apply --profile "Profile 2"
```

By default, the script resolves the Chrome root by OS and picks the last-used profile from `Local State`, falling back to `Default`.

## Safety Model

- `audit` is read-only.
- `apply` refuses to mutate while Google Chrome appears to be running.
- `apply` always creates timestamped backups of `Preferences` and `Cookies` before writing.
- `--dry-run` shows what would change without mutating the profile.

## Behavior Summary

- Writes Apple cookie rules as Chrome `session_only` entries under the profile `Preferences`.
- Removes stale Apple cookie rows from the profile `Cookies` SQLite database.
- Removes Apple-origin state metadata such as site engagement and media engagement from `Preferences`.
- Removes directly identifiable Apple-origin artifacts from origin-keyed storage paths when those paths encode the Apple host in their filenames.
- Does not treat this as a permanent Apple block; the goal is clean next-launch state, not broken Apple login.

## Validation Notes

- On the validated Ubuntu path, the current Chrome profile still contains the intended Apple `session_only` rules.
- On macOS on 2026-04-09, `audit`, `apply --dry-run`, and `apply` succeeded against a real Google Chrome `Default` profile.
- That macOS run created timestamped backups, wrote all 5 Apple `session_only` rules, and reduced Apple cookie rows from 6 to 0.
- While Chrome is open, temporary Apple cookies can still exist. The intended result is cleanup after all Chrome windows fully exit and Chrome starts again.
- Interactive Apple login after reopening Chrome is still an operator follow-up step, because the final account-specific login behavior depends on the user's own Apple flow.
- The script intentionally avoids claiming full surgical cleanup inside opaque Chrome LevelDB stores whose on-disk keys are not safely origin-addressable.

## Privacy Boundary

This repository ships only portable skill logic, metadata, and tests. It does not include private memory files, local personal paths, account data, or captured browser state.

## Repository Layout

- `chrome-apple-session-only-skill/`: Codex skill package
- `README.md`: English overview
- `README.zh-CN.md`: Chinese overview
- `LICENSE`: MIT license
- `tests/`: stdlib unit tests
