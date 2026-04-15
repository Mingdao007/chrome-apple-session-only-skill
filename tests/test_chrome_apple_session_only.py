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


def build_preferences() -> dict:
    return {
        "profile": {
            "content_settings": {
                "exceptions": {
                    "cookies": {
                        "https://apple.com:443,*": {
                            "last_modified": "1",
                            "setting": 1,
                        }
                    },
                    "cookie_controls_metadata": {
                        "https://[*.]apple.com,*": {
                            "last_modified": "2",
                            "setting": {},
                        }
                    },
                    "site_engagement": {
                        "https://appleid.apple.com:443,*": {
                            "last_modified": "3",
                            "setting": {"rawScore": 9.9},
                        }
                    },
                    "media_engagement": {
                        "https://appleid.apple.com:443,*": {
                            "last_modified": "4",
                            "setting": {"visits": 3},
                        }
                    },
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


def build_cookie_rows() -> list[tuple[str, str]]:
    return [
        (".apple.com", "a"),
        ("appleid.apple.com", "b"),
        (".example.com", "c"),
    ]


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
            write_json(profile_path / "Preferences", build_preferences())
            make_cookie_db(profile_path / "Cookies", build_cookie_rows())
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

    def test_apply_dry_run_preserves_files(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            preferences_path = profile_path / "Preferences"
            write_json(preferences_path, build_preferences())
            make_cookie_db(profile_path / "Cookies", build_cookie_rows())

            before_preferences = preferences_path.read_text(encoding="utf-8")
            with mock.patch.object(MODULE, "chrome_running", return_value=False):
                result = MODULE.apply_profile(chrome_root, "apple", dry_run=True)

            after_preferences = preferences_path.read_text(encoding="utf-8")
            self.assertEqual(result["mode"], "dry-run")
            self.assertEqual(before_preferences, after_preferences)
            self.assertEqual(result["planned_cookie_row_removals"], 2)
            self.assertFalse(result["backups"])

    def test_apply_writes_session_only_rules_and_deletes_apple_cookies(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            write_json(profile_path / "Preferences", build_preferences())
            make_cookie_db(profile_path / "Cookies", build_cookie_rows())
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

    def test_apply_refuses_when_chrome_is_running(self) -> None:
        with TemporaryDirectory() as tmp:
            chrome_root = Path(tmp)
            profile_path = chrome_root / "Default"
            write_json(chrome_root / "Local State", build_local_state("Default"))
            write_json(profile_path / "Preferences", build_preferences())
            make_cookie_db(profile_path / "Cookies", [(".apple.com", "a")])

            with mock.patch.object(MODULE, "chrome_running", return_value=True):
                with self.assertRaisesRegex(RuntimeError, "appears to be running"):
                    MODULE.apply_profile(chrome_root, "apple")

    def test_parser_rejects_claude_target(self) -> None:
        parser = MODULE.build_parser()
        with self.assertRaises(SystemExit) as exc:
            parser.parse_args(["audit", "--target", "claude"])
        self.assertNotEqual(exc.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
