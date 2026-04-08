# Platform Paths and Safety

## Supported Chrome Roots

- Ubuntu: `~/.config/google-chrome`
- macOS: `~/Library/Application Support/Google/Chrome`

The script accepts `--chrome-root` for synthetic tests or nonstandard layouts.

## Validation Status

- Ubuntu: live-validated.
- macOS: live-validated on 2026-04-09 against a real Google Chrome `Default` profile.
- The validated macOS run covered `audit`, `apply --dry-run`, and `apply`, including timestamped backups plus post-apply confirmation of 5/5 Apple `session_only` rules and 0 Apple cookie rows.
- Interactive Apple login after reopening Chrome is still an operator verification step, because it depends on the user's own account flow.

## Profile Resolution

Default order:

1. explicit `--profile`
2. `Local State.profile.last_used`
3. `Default`

## Domain Scope

This skill intentionally limits itself to the `apple.com` family:

- `http://apple.com:80,*`
- `http://[*.]apple.com,*`
- `https://apple.com:443,*`
- `https://[*.]apple.com,*`
- `https://appleid.apple.com:443,*`

`icloud.com` is out of scope in v1.

## What `apply` Changes

- Creates timestamped backups of:
  - `Preferences`
  - `Cookies`
- Writes the Apple cookie rules above as Chrome `session_only` entries (`setting: 4`)
- Removes Apple cookie rows from the `Cookies` SQLite database
- Removes Apple-origin metadata from known state buckets in `Preferences`, including:
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
- Removes directly identifiable Apple-origin artifacts from origin-keyed storage names when the host is safely encoded in the path

## What It Does Not Claim

- It does not claim to surgically rewrite every opaque Chrome LevelDB or SQLite store.
- It does not permanently block Apple login.
- It does not manage Chromium, Edge, or non-Google Chrome variants in v1.

## Operational Rule

- `audit` is read-only.
- `apply` refuses to mutate while Google Chrome appears to be running.
- `apply --dry-run` is the no-write preview path.
