#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TARGET_CONFIGS = {
    "apple": {
        "label": "Apple",
        "domains": ["apple.com"],
        "cookie_rule_keys": [
            "http://[*.]apple.com,*",
            "http://apple.com:80,*",
            "https://[*.]apple.com,*",
            "https://apple.com:443,*",
            "https://appleid.apple.com:443,*",
        ],
    },
}

STATE_EXCEPTION_BUCKETS = [
    "cookie_controls_metadata",
    "site_engagement",
    "media_engagement",
    "important_site_info",
    "storage_access",
    "top_level_storage_access",
    "third_party_storage_partitioning",
    "legacy_cookie_access",
    "legacy_cookie_scope",
    "fedcm_idp_registration",
    "fedcm_idp_signin",
    "webid_api",
    "webid_auto_reauthn",
]

DIRECT_ARTIFACT_ROOTS = [
    "IndexedDB",
    "Local Storage",
    "WebStorage",
    "Session Storage",
    "Service Worker",
    "Storage",
]


def default_chrome_root(platform_name: str | None = None, home: Path | None = None) -> Path:
    platform_name = platform_name or sys.platform
    home = home or Path.home()
    if platform_name.startswith("linux"):
        return home / ".config" / "google-chrome"
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome"
    raise ValueError(f"Unsupported platform: {platform_name}")


def chrome_timestamp_now() -> str:
    chrome_epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - chrome_epoch
    return str(int(delta.total_seconds() * 1_000_000))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_profile(chrome_root: Path, profile_override: str | None = None) -> tuple[str, Path, Path]:
    local_state_path = chrome_root / "Local State"
    if profile_override:
        profile_name = profile_override
    else:
        profile_name = "Default"
        if local_state_path.is_file():
            try:
                local_state = read_json(local_state_path)
                profile_name = str(local_state.get("profile", {}).get("last_used") or "Default")
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                profile_name = "Default"
    return profile_name, chrome_root / profile_name, local_state_path


def target_config(name: str) -> dict[str, Any]:
    try:
        return TARGET_CONFIGS[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported target: {name}") from exc


def content_setting_hosts(key: str) -> list[str]:
    if not isinstance(key, str):
        return []
    hosts: list[str] = []
    for pattern in key.split(","):
        pattern = pattern.strip()
        if not pattern or pattern == "*":
            continue
        if "://" in pattern:
            pattern = pattern.split("://", 1)[1]
        if pattern.startswith("[*.]"):
            pattern = pattern[4:]
        host = pattern.split(":", 1)[0].strip().lower()
        if host:
            hosts.append(host)
    return hosts


def is_target_domain(host: str | None, domains: list[str]) -> bool:
    if not host:
        return False
    host = host.strip().lower().lstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def is_target_content_setting_key(key: str, domains: list[str]) -> bool:
    return any(is_target_domain(host, domains) for host in content_setting_hosts(key))


def is_target_cookie_host(host: str | None, domains: list[str]) -> bool:
    if not host:
        return False
    host = host.strip().lower().lstrip(".")
    return is_target_domain(host, domains)


def extract_host_from_origin_artifact_name(name: str) -> str | None:
    pieces = name.split("_", 2)
    if len(pieces) < 3:
        return None
    if pieces[0] not in {"http", "https", "ws", "wss"}:
        return None
    return pieces[1].strip().lower()


def chrome_running() -> bool:
    try:
        result = subprocess.run(
            ["ps", "-A", "-o", "command="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return False

    lines = [line.strip().lower() for line in result.stdout.splitlines()]
    for line in lines:
        if "google chrome" in line or "google-chrome" in line:
            if "chrome_apple_session_only.py" not in line:
                return True
    return False


def collect_cookie_rows(cookie_db_path: Path, domains: list[str]) -> tuple[list[tuple[int, str]], str | None]:
    if not cookie_db_path.is_file():
        return [], None

    try:
        conn = sqlite3.connect(f"file:{cookie_db_path}?mode=ro", uri=True)
        try:
            rows = conn.execute("SELECT rowid, host_key FROM cookies").fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return [], str(exc)

    hits = [(int(rowid), str(host_key)) for rowid, host_key in rows if is_target_cookie_host(str(host_key), domains)]
    return hits, None


def count_direct_origin_artifacts(profile_path: Path, domains: list[str]) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for root_name in DIRECT_ARTIFACT_ROOTS:
        root_path = profile_path / root_name
        if not root_path.exists():
            continue

        hits: list[str] = []
        search_roots = [root_path]
        search_roots.extend(child for child in root_path.iterdir() if child.is_dir())
        for directory in search_roots:
            for child in directory.iterdir():
                host = extract_host_from_origin_artifact_name(child.name)
                if is_target_domain(host, domains):
                    hits.append(str(child))
        if hits:
            matches[root_name] = sorted(set(hits))
    return matches


def audit_profile(chrome_root: Path, target: str, profile_override: str | None = None) -> dict[str, Any]:
    chrome_root = chrome_root.expanduser()
    config = target_config(target)
    domains = list(config["domains"])
    cookie_rule_keys = list(config["cookie_rule_keys"])
    profile_name, profile_path, local_state_path = resolve_profile(chrome_root, profile_override)
    preferences_path = profile_path / "Preferences"
    cookies_path = profile_path / "Cookies"

    if not profile_path.is_dir():
        raise FileNotFoundError(f"Chrome profile not found: {profile_path}")
    if not preferences_path.is_file():
        raise FileNotFoundError(f"Preferences file not found: {preferences_path}")

    preferences = read_json(preferences_path)
    exceptions = preferences.get("profile", {}).get("content_settings", {}).get("exceptions", {})
    cookie_rules = exceptions.get("cookies", {}) if isinstance(exceptions.get("cookies", {}), dict) else {}

    present_rules: dict[str, Any] = {}
    missing_rules: list[str] = []
    non_session_only_rules: dict[str, Any] = {}
    for key in cookie_rule_keys:
        rule = cookie_rules.get(key)
        if isinstance(rule, dict) and rule.get("setting") == 4:
            present_rules[key] = rule
        else:
            missing_rules.append(key)
            if rule is not None:
                non_session_only_rules[key] = rule

    state_bucket_hits: dict[str, list[str]] = {}
    for bucket in STATE_EXCEPTION_BUCKETS:
        items = exceptions.get(bucket, {})
        if not isinstance(items, dict):
            continue
        hits = sorted(key for key in items if is_target_content_setting_key(key, domains))
        if hits:
            state_bucket_hits[bucket] = hits

    cookie_rows, cookie_db_error = collect_cookie_rows(cookies_path, domains)
    cookie_host_counts = dict(sorted(Counter(host for _, host in cookie_rows).items()))

    return {
        "target": target,
        "target_label": config["label"],
        "target_domains": domains,
        "chrome_root": str(chrome_root),
        "local_state_path": str(local_state_path),
        "profile_name": profile_name,
        "profile_path": str(profile_path),
        "preferences_path": str(preferences_path),
        "cookies_path": str(cookies_path),
        "chrome_running": chrome_running(),
        "cookie_rules": {
            "expected_count": len(cookie_rule_keys),
            "present": present_rules,
            "missing": missing_rules,
            "non_session_only": non_session_only_rules,
        },
        "cookie_row_count": len(cookie_rows),
        "cookie_host_counts": cookie_host_counts,
        "cookie_db_error": cookie_db_error,
        "state_bucket_hits": state_bucket_hits,
        "direct_origin_artifacts": count_direct_origin_artifacts(profile_path, domains),
    }


def ensure_cookie_rules(preferences: dict[str, Any], target: str) -> dict[str, Any]:
    config = target_config(target)
    domains = list(config["domains"])
    cookie_rule_keys = list(config["cookie_rule_keys"])
    profile = preferences.setdefault("profile", {})
    content_settings = profile.setdefault("content_settings", {})
    exceptions = content_settings.setdefault("exceptions", {})
    cookie_rules = exceptions.setdefault("cookies", {})
    if not isinstance(cookie_rules, dict):
        cookie_rules = {}
        exceptions["cookies"] = cookie_rules

    removed_keys = sorted(key for key in list(cookie_rules) if is_target_content_setting_key(key, domains))
    for key in removed_keys:
        cookie_rules.pop(key, None)

    last_modified = chrome_timestamp_now()
    for key in cookie_rule_keys:
        cookie_rules[key] = {
            "last_modified": last_modified,
            "setting": 4,
        }

    return {
        "removed_keys": removed_keys,
        "written_keys": cookie_rule_keys,
    }


def remove_state_bucket_entries(preferences: dict[str, Any], target: str) -> dict[str, list[str]]:
    domains = list(target_config(target)["domains"])
    exceptions = preferences.setdefault("profile", {}).setdefault("content_settings", {}).setdefault("exceptions", {})
    removed: dict[str, list[str]] = {}
    for bucket in STATE_EXCEPTION_BUCKETS:
        items = exceptions.get(bucket)
        if not isinstance(items, dict):
            continue
        hits = sorted(key for key in list(items) if is_target_content_setting_key(key, domains))
        if not hits:
            continue
        for key in hits:
            items.pop(key, None)
        removed[bucket] = hits
    return removed


def backup_file(path: Path, timestamp: str, target: str) -> str | None:
    if not path.exists():
        return None
    backup_path = path.with_name(f"{path.name}.backup.{target}-session-only.{timestamp}")
    shutil.copy2(path, backup_path)
    return str(backup_path)


def delete_cookie_rows(cookie_db_path: Path, target: str) -> tuple[int, str | None]:
    domains = list(target_config(target)["domains"])
    if not cookie_db_path.is_file():
        return 0, None

    try:
        conn = sqlite3.connect(cookie_db_path)
        try:
            rows = conn.execute("SELECT rowid, host_key FROM cookies").fetchall()
            rowids = [int(rowid) for rowid, host_key in rows if is_target_cookie_host(str(host_key), domains)]
            if rowids:
                placeholders = ", ".join("?" for _ in rowids)
                conn.execute(f"DELETE FROM cookies WHERE rowid IN ({placeholders})", rowids)
                conn.commit()
            return len(rowids), None
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return 0, str(exc)


def delete_direct_origin_artifacts(profile_path: Path, target: str) -> list[str]:
    removed: list[str] = []
    domains = list(target_config(target)["domains"])
    for paths in count_direct_origin_artifacts(profile_path, domains).values():
        for raw_path in paths:
            path = Path(raw_path)
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            removed.append(str(path))
    return sorted(set(removed))


def apply_profile(chrome_root: Path, target: str, profile_override: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    report = audit_profile(chrome_root, target, profile_override)
    if report["chrome_running"] and not dry_run:
        raise RuntimeError("Google Chrome appears to be running. Close it before apply.")

    preferences_path = Path(report["preferences_path"])
    cookies_path = Path(report["cookies_path"])
    preferences = read_json(preferences_path)
    preferences_copy = copy.deepcopy(preferences)

    rule_summary = ensure_cookie_rules(preferences_copy, target)
    removed_state = remove_state_bucket_entries(preferences_copy, target)
    direct_artifacts = count_direct_origin_artifacts(Path(report["profile_path"]), list(target_config(target)["domains"]))
    cookie_rows, cookie_db_error = collect_cookie_rows(cookies_path, list(target_config(target)["domains"]))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result: dict[str, Any] = {
        "mode": "dry-run" if dry_run else "apply",
        "report_before": report,
        "planned_cookie_rules": rule_summary,
        "planned_state_removals": removed_state,
        "planned_cookie_row_removals": len(cookie_rows),
        "planned_direct_artifact_removals": direct_artifacts,
        "cookie_db_error": cookie_db_error,
        "backups": [],
    }

    if dry_run:
        return result

    backups = [
        backup_file(preferences_path, timestamp, target),
        backup_file(cookies_path, timestamp, target),
    ]
    result["backups"] = [item for item in backups if item]

    write_json(preferences_path, preferences_copy)
    removed_cookie_rows, cookie_delete_error = delete_cookie_rows(cookies_path, target)
    removed_artifacts = delete_direct_origin_artifacts(Path(report["profile_path"]), target)
    result["removed_cookie_rows"] = removed_cookie_rows
    result["cookie_delete_error"] = cookie_delete_error
    result["removed_direct_artifacts"] = removed_artifacts
    result["report_after"] = audit_profile(chrome_root, target, profile_override)
    return result


def print_audit(report: dict[str, Any]) -> None:
    label = report["target_label"]
    print("Mode: audit")
    print(f"Target: {label}")
    print(f"Chrome root: {report['chrome_root']}")
    print(f"Profile: {report['profile_name']}")
    print(f"Profile path: {report['profile_path']}")
    print(f"Preferences: {report['preferences_path']}")
    print(f"Cookies DB: {report['cookies_path']}")
    print(f"Chrome running: {'yes' if report['chrome_running'] else 'no'}")
    print(
        f"{label} session-only rules: "
        f"{len(report['cookie_rules']['present'])}/{report['cookie_rules']['expected_count']} present"
    )
    if report["cookie_rules"]["missing"]:
        print("Missing rules:")
        for key in report["cookie_rules"]["missing"]:
            print(f"  - {key}")
    print(f"{label} cookie rows: {report['cookie_row_count']}")
    if report["cookie_host_counts"]:
        print(f"{label} cookie host counts:")
        for host, count in report["cookie_host_counts"].items():
            print(f"  - {host}: {count}")
    if report["cookie_db_error"]:
        print(f"Cookie DB error: {report['cookie_db_error']}")
    if report["state_bucket_hits"]:
        print(f"{label} state metadata hits:")
        for bucket, hits in report["state_bucket_hits"].items():
            print(f"  - {bucket}: {len(hits)}")
    if report["direct_origin_artifacts"]:
        print(f"Direct {label}-origin artifacts:")
        for root_name, hits in report["direct_origin_artifacts"].items():
            print(f"  - {root_name}: {len(hits)}")


def print_apply(result: dict[str, Any]) -> None:
    mode = result["mode"]
    print(f"Mode: {mode}")
    before = result["report_before"]
    label = before["target_label"]
    print(f"Target: {label}")
    print(f"Profile: {before['profile_name']}")
    print(f"Chrome running: {'yes' if before['chrome_running'] else 'no'}")
    print(f"Planned cookie rule writes: {len(result['planned_cookie_rules']['written_keys'])}")
    print(f"Planned state metadata removals: {sum(len(v) for v in result['planned_state_removals'].values())}")
    print(f"Planned cookie row removals: {result['planned_cookie_row_removals']}")
    print(
        "Planned direct artifact removals: "
        f"{sum(len(v) for v in result['planned_direct_artifact_removals'].values())}"
    )
    if result["cookie_db_error"]:
        print(f"Cookie DB error: {result['cookie_db_error']}")
    if mode == "dry-run":
        return
    if result["backups"]:
        print("Backups:")
        for path in result["backups"]:
            print(f"  - {path}")
    print(f"Removed cookie rows: {result.get('removed_cookie_rows', 0)}")
    print(f"Removed direct artifacts: {len(result.get('removed_direct_artifacts', []))}")
    if result.get("cookie_delete_error"):
        print(f"Cookie delete error: {result['cookie_delete_error']}")
    after = result.get("report_after")
    if after is not None:
        print(f"{label} cookie rows after apply: {after['cookie_row_count']}")
        print(
            f"{label} session-only rules after apply: "
            f"{len(after['cookie_rules']['present'])}/{after['cookie_rules']['expected_count']} present"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit or apply Apple session-only cleanup for Google Chrome.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("audit", "apply"):
        sub_parser = sub.add_parser(name)
        sub_parser.add_argument("--profile", default=None, help="Chrome profile name, e.g. Default or Profile 2")
        sub_parser.add_argument("--chrome-root", default=None, help="Override the Google Chrome root path")
        sub_parser.add_argument(
            "--target",
            choices=sorted(TARGET_CONFIGS),
            default="apple",
            help="Target domain family to clean up; only apple is supported",
        )

    sub.choices["apply"].add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    chrome_root = Path(args.chrome_root).expanduser() if args.chrome_root else default_chrome_root()

    try:
        if args.command == "audit":
            print_audit(audit_profile(chrome_root, args.target, args.profile))
            return 0
        if args.command == "apply":
            print_apply(apply_profile(chrome_root, args.target, args.profile, dry_run=args.dry_run))
            return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
