# Platform Paths and Safety

## Supported Chrome Roots

- Ubuntu: `~/.config/google-chrome`
- macOS: `~/Library/Application Support/Google/Chrome`

The script accepts `--chrome-root` for synthetic tests or nonstandard layouts.

## Validation Status

- Ubuntu: live-validated.
- macOS Apple target: live-validated on 2026-04-09 against a real Google Chrome `Default` profile.
- macOS Claude target: live-validated on 2026-04-14 against a real Google Chrome `Default` profile.
- The validated Apple macOS run covered `audit`, `apply --dry-run`, and `apply`, including timestamped backups plus post-apply confirmation of 5/5 Apple `session_only` rules and 0 Apple cookie rows.
- The validated Claude macOS run covered `audit`, `apply --dry-run`, and `apply`, including timestamped backups plus post-apply confirmation of 12/12 Claude-family `session_only` rules and 0 Claude-family cookie rows.
- Interactive Apple or Claude login after reopening Chrome is still an operator verification step, because it depends on the user's own account flow.

## Profile Resolution

Default order:

1. explicit `--profile`
2. `Local State.profile.last_used`
3. `Default`

## Domain Scope

This skill intentionally limits itself to two fixed targets:

Default `apple` target:

- `http://apple.com:80,*`
- `http://[*.]apple.com,*`
- `https://apple.com:443,*`
- `https://[*.]apple.com,*`
- `https://appleid.apple.com:443,*`

Optional `claude` target:

- `http://claude.ai:80,*`
- `http://[*.]claude.ai,*`
- `https://claude.ai:443,*`
- `https://[*.]claude.ai,*`
- `http://claude.com:80,*`
- `http://[*.]claude.com,*`
- `https://claude.com:443,*`
- `https://[*.]claude.com,*`
- `http://anthropic.com:80,*`
- `http://[*.]anthropic.com,*`
- `https://anthropic.com:443,*`
- `https://[*.]anthropic.com,*`

`icloud.com` and any domain outside those two target families are out of scope.

## What `apply` Changes

- Creates timestamped backups of:
  - `Preferences`
  - `Cookies`
- Writes the selected target cookie rules above as Chrome `session_only` entries (`setting: 4`)
- Removes target cookie rows from the `Cookies` SQLite database
- Removes target-origin metadata from known state buckets in `Preferences`, including:
  - `cookie_controls_metadata`
  - `site_engagement`
  - `media_engagement`
  - `important_site_info`
  - `storage_access`
  - `top_level_storage_access`
  - `third_party_storage_partitioning`
  - `legacy_cookie_access`
  - `legacy_cookie_scope`
  - `fedcm_idp_registration`
  - `fedcm_idp_signin`
  - `webid_api`
  - `webid_auto_reauthn`
- Removes directly identifiable target-origin artifacts from origin-keyed storage names when the host is safely encoded in the path

## What It Does Not Claim

- It does not claim to surgically rewrite every opaque Chrome LevelDB or SQLite store.
- It does not permanently block Apple, Claude, or Anthropic login.
- It does not manage Chromium, Edge, or non-Google Chrome variants in v1.

## Operational Rule

- `audit` is read-only.
- `apply` refuses to mutate while Google Chrome appears to be running.
- `apply --dry-run` is the no-write preview path.
