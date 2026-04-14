from __future__ import annotations

import importlib.util
import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "chrome-apple-session-only-skill"
    / "scripts"
    / "chrome_apple_session_only.py"
)

SPEC = importlib.util.spec_from_file_location("chrome_apple_session_only", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_preferences(target: str) -> dict:
    if target == "apple":
        cookies = {
            "https://apple.com:443,*": {
                "last_modified": "1",
                "setting": 1,
            }
        }
        cookie_controls_metadata = {
            "https://[*.]apple.com,*": {
                "last_modified": "2",
                "setting": {},
            }
        }
        site_engagement = {
            "https://appleid.apple.com:443,*": {
                "last_modified": "3",
                "setting": {"rawScore": 9.9},
            }
        }
        media_engagement = {
            "https://appleid.apple.com:443,*": {
                "last_modified": "4",
                "setting": {"visits": 3},
            }
        }
        webid_auto_reauthn = {}
    elif target == "claude":
        cookies = {
            "https://claude.ai:443,*": {
                "last_modified": "10",
                "setting": 1,
            }
        }
        cookie_controls_metadata = {
            "https://[*.]google.com,https://[*.]claude.ai": {
                "last_modified": "11",
                "setting": {},
            },
            "https://[*.]anthropic.com,*": {
                "last_modified": "12",
                "setting": {},
            },
        }
        site_engagement = {
            "https://platform.claude.com:443,*": {
                "last_modified": "13",
                "setting": {"rawScore": 4.2},
            }
        }
        media_engagement = {
            "https://claude.com:443,*": {
                "last_modified": "14",
                "setting": {"visits": 5},
            },
            "https://www.anthropic.com:443,*": {
                "last_modified": "15",
                "setting": {"visits": 2},
            },
        }
        webid_auto_reauthn = {
            "https://[*.]claude.ai,*": {
                "last_modified": "16",
                "setting": {},
            }
        }
    else:
        raise ValueError(f"Unsupported target: {target}")

    return {
        "profile": {
            "content_settings": {
                "exceptions": {
                    "cookies": cookies,
                    "cookie_controls_metadata": cookie_controls_metadata,
                    "site_engagement": site_engagement,
                    "media_engagement": media_engagement,
                    "webid_auto_reauthn": webid_auto_reauthn,
                    "notifications": {
                        "https://www.example.com:443,*": {
                            "last_modified": "99",
                            "setting": 1,
                        }
                    },
                }
            }
        }
    }


def build_local_state(last_used: str = "Profile 2") -> dict:
    return {
        "profile": {
            "last_used": last_used,
            "info_cache": {
                last_used: {"name": last_used},
                "Default": {"name": "Default"},
            },
        }
    }


def make_cookie_db(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
        conn.executemany("INSERT INTO cookies(host_key, name) VALUES (?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def build_cookie_rows(target: str) -> list[tuple[str, str]]:
    if target == "apple":
        return [
            (".apple.com", "a"),
            ("appleid.apple.com", "b"),
            (".example.com", "c"),
        ]
    if target == "claude":
        return [
            (".claude.ai", "a"),
            ("platform.claude.com", "b"),
            (".anthropic.com", "c"),
            (".example.com", "d"),
        ]
    raise ValueError(f"Unsupported target: {target}")


class ChromeAppleSessionOnlyTests(unittest.TestCase):
    def test_default_chrome_root_resolves_macos(self) -> None:
        home = Path("/Users/tester")
        root = MODULE.default_chrome_root(platform_name="darwin", home=home)
        self.assertEqual(root, home / "Library" / "Application Support" / "Google" / "Chrome")

    def test_audit_prefers_last_used_profile(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Profile 2"
            write_json(chrome_root / "Local State", build_local_state("Profile 2"))
            write_json(profile_path / "Preferences", build_preferences("apple"))
            make_cookie_db(profile_path / "Cookies", build_cookie_rows("apple"))
            (profile_path / "IndexedDB" / "https_appleid.apple.com_0.indexeddb.leveldb").mkdir(parents=True)

            with mock.patch.object(MODULE, "chrome_running", return_value=False):
                report = MODULE.audit_profile(chrome_root, "apple")

            self.assertEqual(report["profile_name"], "Profile 2")
            self.assertEqual(report["cookie_row_count"], 2)
            self.assertIn("https://appleid.apple.com:443,*", report["cookie_rules"]["missing"])
            self.assertEqual(report["state_bucket_hits"]["site_engagement"], ["https://appleid.apple.com:443,*"])
            self.assertEqual(
                report["direct_origin_artifacts"]["IndexedDB"],
                [str(profile_path / "IndexedDB" / "https_appleid.apple.com_0.indexeddb.leveldb")],
            )

    def test_audit_claude_target_matches_multiple_domains_and_dual_origin_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            write_json(profile_path / "Preferences", build_preferences("claude"))
            make_cookie_db(profile_path / "Cookies", build_cookie_rows("claude"))
            (profile_path / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb").mkdir(parents=True)

            with mock.patch.object(MODULE, "chrome_running", return_value=False):
                report = MODULE.audit_profile(chrome_root, "claude")

            self.assertEqual(report["target"], "claude")
            self.assertEqual(report["cookie_row_count"], 3)
            self.assertEqual(
                report["cookie_host_counts"],
                {
                    ".anthropic.com": 1,
                    ".claude.ai": 1,
                    "platform.claude.com": 1,
                },
            )
            self.assertIn(
                "https://[*.]google.com,https://[*.]claude.ai",
                report["state_bucket_hits"]["cookie_controls_metadata"],
            )
            self.assertIn("https://platform.claude.com:443,*", report["state_bucket_hits"]["site_engagement"])
            self.assertEqual(
                report["direct_origin_artifacts"]["IndexedDB"],
                [str(profile_path / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb")],
            )

    def test_apply_dry_run_preserves_files(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            preferences_path = profile_path / "Preferences"
            write_json(preferences_path, build_preferences("apple"))
            make_cookie_db(profile_path / "Cookies", build_cookie_rows("apple"))

            before_preferences = preferences_path.read_text(encoding="utf-8")
            with mock.patch.object(MODULE, "chrome_running", return_value=False):
                result = MODULE.apply_profile(chrome_root, "apple", dry_run=True)

            after_preferences = preferences_path.read_text(encoding="utf-8")
            self.assertEqual(result["mode"], "dry-run")
            self.assertEqual(before_preferences, after_preferences)
            self.assertEqual(result["planned_cookie_row_removals"], 2)
            self.assertFalse(result["backups"])

    def test_apply_claude_dry_run_preserves_files(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            preferences_path = profile_path / "Preferences"
            write_json(preferences_path, build_preferences("claude"))
            make_cookie_db(profile_path / "Cookies", build_cookie_rows("claude"))

            before_preferences = preferences_path.read_text(encoding="utf-8")
            with mock.patch.object(MODULE, "chrome_running", return_value=False):
                result = MODULE.apply_profile(chrome_root, "claude", dry_run=True)

            after_preferences = preferences_path.read_text(encoding="utf-8")
            self.assertEqual(result["mode"], "dry-run")
            self.assertEqual(before_preferences, after_preferences)
            self.assertEqual(result["planned_cookie_row_removals"], 3)
            self.assertFalse(result["backups"])

    def test_apply_writes_session_only_rules_and_deletes_apple_cookies(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            write_json(profile_path / "Preferences", build_preferences("apple"))
            make_cookie_db(profile_path / "Cookies", build_cookie_rows("apple"))
            artifact = profile_path / "IndexedDB" / "https_appleid.apple.com_0.indexeddb.leveldb"
            artifact.mkdir(parents=True)

            with mock.patch.object(MODULE, "chrome_running", return_value=False):
                result = MODULE.apply_profile(chrome_root, "apple")

            preferences = json.loads((profile_path / "Preferences").read_text(encoding="utf-8"))
            cookie_rules = preferences["profile"]["content_settings"]["exceptions"]["cookies"]
            for key in MODULE.TARGET_CONFIGS["apple"]["cookie_rule_keys"]:
                self.assertEqual(cookie_rules[key]["setting"], 4)
            self.assertNotIn(
                "https://appleid.apple.com:443,*",
                preferences["profile"]["content_settings"]["exceptions"]["site_engagement"],
            )
            self.assertTrue(result["backups"])
            self.assertEqual(result["removed_cookie_rows"], 2)
            self.assertFalse(artifact.exists())
            self.assertEqual(result["report_after"]["cookie_row_count"], 0)

            conn = sqlite3.connect(profile_path / "Cookies")
            try:
                rows = conn.execute("SELECT host_key FROM cookies ORDER BY host_key").fetchall()
            finally:
                conn.close()
            self.assertEqual(rows, [(".example.com",)])

    def test_apply_writes_session_only_rules_and_deletes_claude_cookies(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            write_json(profile_path / "Preferences", build_preferences("claude"))
            make_cookie_db(profile_path / "Cookies", build_cookie_rows("claude"))
            artifact = profile_path / "IndexedDB" / "https_claude.ai_0.indexeddb.leveldb"
            artifact.mkdir(parents=True)

            with mock.patch.object(MODULE, "chrome_running", return_value=False):
                result = MODULE.apply_profile(chrome_root, "claude")

            preferences = json.loads((profile_path / "Preferences").read_text(encoding="utf-8"))
            cookie_rules = preferences["profile"]["content_settings"]["exceptions"]["cookies"]
            for key in MODULE.TARGET_CONFIGS["claude"]["cookie_rule_keys"]:
                self.assertEqual(cookie_rules[key]["setting"], 4)
            self.assertNotIn(
                "https://[*.]google.com,https://[*.]claude.ai",
                preferences["profile"]["content_settings"]["exceptions"]["cookie_controls_metadata"],
            )
            self.assertNotIn(
                "https://platform.claude.com:443,*",
                preferences["profile"]["content_settings"]["exceptions"]["site_engagement"],
            )
            self.assertTrue(result["backups"])
            self.assertEqual(result["removed_cookie_rows"], 3)
            self.assertFalse(artifact.exists())
            self.assertEqual(result["report_after"]["cookie_row_count"], 0)

            conn = sqlite3.connect(profile_path / "Cookies")
            try:
                rows = conn.execute("SELECT host_key FROM cookies ORDER BY host_key").fetchall()
            finally:
                conn.close()
            self.assertEqual(rows, [(".example.com",)])

    def test_apply_refuses_when_chrome_is_running(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            write_json(profile_path / "Preferences", build_preferences("apple"))
            make_cookie_db(profile_path / "Cookies", [(".apple.com", "a")])

            with mock.patch.object(MODULE, "chrome_running", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "appears to be running"):
                    MODULE.apply_profile(chrome_root, "apple")

    def test_apply_claude_refuses_when_chrome_is_running(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            write_json(profile_path / "Preferences", build_preferences("claude"))
            make_cookie_db(profile_path / "Cookies", [(".claude.ai", "a")])

            with mock.patch.object(MODULE, "chrome_running", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "appears to be running"):
                    MODULE.apply_profile(chrome_root, "claude")


if __name__ == "__main__":
    unittest.main()
