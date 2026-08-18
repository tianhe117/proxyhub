"""Tests for app/settings.py — covers every public interface.

Run with:
    python3 -m unittest discover -s test -v

This is a throwaway test environment: tests mutate the real data/setting.json
in place (no temp-dir isolation). reset_to_defaults() runs in setUp/tearDown
so each test starts and ends from DEFAULT_SETTINGS.
"""

import json
import os
import unittest
from importlib import reload

from app import settings


class TestConstants(unittest.TestCase):
    """Module-level constants exist with expected types/values."""

    def test_default_settings_is_dict_of_strings(self):
        self.assertIsInstance(settings.DEFAULT_SETTINGS, dict)
        self.assertTrue(settings.DEFAULT_SETTINGS)  # non-empty
        for k, v in settings.DEFAULT_SETTINGS.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, str)

    def test_default_settings_expected_keys(self):
        expected = {
            'check_interval_normal', 'check_interval_failover',
            'tcp_timeout', 'curl_timeout', 'test_url',
            'web_port', 'web_username', 'web_password',
        }
        self.assertEqual(set(settings.DEFAULT_SETTINGS), expected)

    def test_singbox_binary_constants(self):
        self.assertEqual(settings.SINGBOX_VERSION_ARGS, ['version'])
        self.assertEqual(settings.SINGBOX_RUN_ARGS, ['run', '-c', '{config}'])

    def test_github_release_constants(self):
        self.assertEqual(settings.SINGBOX_REPO, 'SagerNet/sing-box')
        self.assertEqual(settings.SINGBOX_ASSET_PATTERNS,
                         {'linux-64': ['linux-amd64', 'linux-x64']})

    def test_supported_protocols(self):
        self.assertEqual(
            settings.SUPPORTED_PROTOCOLS,
            ('vmess', 'vless', 'trojan', 'ss', 'hysteria2', 'tuic', 'direct'))

    def test_valid_inbound_protocols(self):
        self.assertEqual(settings.VALID_INBOUND_PROTOCOLS,
                         ('http', 'socks', 'ss', 'vmess'))

    def test_base_dir_resolved(self):
        self.assertTrue(settings.BASE_DIR)
        self.assertTrue(os.path.isabs(settings.BASE_DIR))


class TestPathConstants(unittest.TestCase):
    """All path constants are anchored under BASE_DIR (no get_* helpers)."""

    def test_data_dir(self):
        self.assertEqual(settings.DATA_DIR,
                         os.path.join(settings.BASE_DIR, 'data'))

    def test_logs_dir(self):
        self.assertEqual(settings.LOGS_DIR,
                         os.path.join(settings.BASE_DIR, 'logs'))

    def test_singbox_bin_dir(self):
        self.assertEqual(settings.SINGBOX_BIN_DIR,
                         os.path.join(settings.BASE_DIR, 'data', 'bin'))

    def test_singbox_bin_path(self):
        self.assertEqual(settings.SINGBOX_BIN_PATH,
                         os.path.join(settings.BASE_DIR, 'data', 'bin', 'sing-box'))

    def test_config_path(self):
        self.assertEqual(settings.CONFIG_PATH,
                         os.path.join(settings.BASE_DIR, 'data', 'config.json'))

    def test_settings_path(self):
        self.assertEqual(settings.SETTINGS_PATH,
                         os.path.join(settings.BASE_DIR, 'data', 'setting.json'))

    def test_db_path(self):
        self.assertEqual(settings.DB_PATH,
                         os.path.join(settings.BASE_DIR, 'data', 'proxyhub.db'))

    def test_pid_dir(self):
        # PID dir is the data dir itself (no separate subdir).
        self.assertEqual(settings.PID_DIR, settings.DATA_DIR)


class TestLoadAndPersist(unittest.TestCase):
    """_load_from_disk / _persist_to_disk / module-level _store."""

    def setUp(self):
        self.path = settings.SETTINGS_PATH
        self.assertTrue(os.path.exists(self.path), 'settings file must exist')

    def test_store_loaded_at_import(self):
        self.assertIsInstance(settings._store, dict)
        self.assertTrue(settings._store)

    def test_store_matches_disk(self):
        with open(self.path) as f:
            on_disk = json.load(f)
        self.assertEqual(settings._store, on_disk)

    def test_persist_writes_sorted_indented_json(self):
        payload = {'z': '1', 'a': '2'}
        settings._persist_to_disk(payload)
        with open(self.path) as f:
            raw = f.read()
        # sort_keys=True → 'a' before 'z'; indent=2 → newline present.
        self.assertLess(raw.index('  "a"'), raw.index('  "z"'))
        with open(self.path) as f:
            self.assertEqual(json.load(f), payload)

    def test_persist_is_atomic_via_tmp_replace(self):
        settings._persist_to_disk({'k': 'v'})
        # tmp file should not linger after replace.
        self.assertFalse(os.path.exists(self.path + '.tmp'))

    def test_persist_creates_parent_dir(self):
        # Point the module's path at a missing parent and ensure it's created.
        orig = settings.SETTINGS_PATH
        missing = os.path.join(settings.DATA_DIR, 'nested', 'setting.json')
        settings.SETTINGS_PATH = missing
        try:
            settings._persist_to_disk({'x': '1'})
            self.assertTrue(os.path.exists(missing))
            with open(missing) as f:
                self.assertEqual(json.load(f), {'x': '1'})
        finally:
            settings.SETTINGS_PATH = orig
            os.remove(missing)
            os.rmdir(os.path.dirname(missing))

    def test_load_from_disk_returns_defaults_when_missing(self):
        os.replace(self.path, self.path + '.bak')
        try:
            loaded = settings._load_from_disk()
            self.assertEqual(loaded, settings.DEFAULT_SETTINGS)
            # Should have recreated the file from defaults.
            self.assertTrue(os.path.exists(self.path))
        finally:
            if os.path.exists(self.path + '.bak'):
                os.replace(self.path + '.bak', self.path)

    def test_load_from_disk_recovers_from_corrupt_json(self):
        os.replace(self.path, self.path + '.bak')
        with open(self.path, 'w') as f:
            f.write('{ not valid json')
        try:
            loaded = settings._load_from_disk()
            self.assertEqual(loaded, settings.DEFAULT_SETTINGS)
        finally:
            os.replace(self.path + '.bak', self.path)

    def test_load_from_disk_reads_existing_file(self):
        with open(self.path, 'w') as f:
            json.dump({'custom': '99'}, f)
        try:
            self.assertEqual(settings._load_from_disk(), {'custom': '99'})
        finally:
            settings._persist_to_disk(settings.DEFAULT_SETTINGS)

    def test_reload_picks_up_disk_changes(self):
        # Mutate disk, reload module → _store reflects new file.
        with open(self.path, 'w') as f:
            json.dump({'reloaded': '1'}, f)
        try:
            reload(settings)
            self.assertEqual(settings._store, {'reloaded': '1'})
        finally:
            settings._persist_to_disk(settings.DEFAULT_SETTINGS)
            reload(settings)


class TestPublicAPI(unittest.TestCase):
    """get/set/get_all/update/reset behaviour + memory/disk sync."""

    def setUp(self):
        settings.reset_to_defaults()

    def tearDown(self):
        settings.reset_to_defaults()

    def test_get_setting_returns_value(self):
        self.assertEqual(settings.get_setting('web_port'), '8080')
        self.assertEqual(settings.get_setting('web_username'), 'admin')

    def test_get_setting_unknown_key_returns_none(self):
        self.assertIsNone(settings.get_setting('does_not_exist'))

    def test_set_setting_updates_memory_and_disk(self):
        settings.set_setting('web_port', '9090')
        self.assertEqual(settings.get_setting('web_port'), '9090')
        with open(settings.SETTINGS_PATH) as f:
            self.assertEqual(json.load(f)['web_port'], '9090')

    def test_set_setting_coerces_to_string(self):
        settings.set_setting('tcp_timeout', 7)  # int
        self.assertEqual(settings.get_setting('tcp_timeout'), '7')
        self.assertIsInstance(settings.get_setting('tcp_timeout'), str)

    def test_set_setting_creates_new_key(self):
        settings.set_setting('new_key', 'new_val')
        self.assertEqual(settings.get_setting('new_key'), 'new_val')

    def test_get_all_settings_returns_copy(self):
        snapshot = settings.get_all_settings()
        self.assertEqual(snapshot, settings._store)
        snapshot['mutated'] = 'x'
        # Mutating the returned dict must not touch the live store.
        self.assertNotIn('mutated', settings._store)

    def test_update_settings_applies_batch(self):
        settings.update_settings({'web_port': '1111', 'tcp_timeout': '9'})
        self.assertEqual(settings.get_setting('web_port'), '1111')
        self.assertEqual(settings.get_setting('tcp_timeout'), '9')
        with open(settings.SETTINGS_PATH) as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk['web_port'], '1111')
        self.assertEqual(on_disk['tcp_timeout'], '9')

    def test_update_settings_coerces_all_values(self):
        settings.update_settings({'a': 1, 'b': True})
        self.assertEqual(settings.get_setting('a'), '1')
        self.assertEqual(settings.get_setting('b'), 'True')

    def test_update_settings_empty_dict_is_noop(self):
        before = settings.get_all_settings()
        settings.update_settings({})
        self.assertEqual(settings.get_all_settings(), before)

    def test_reset_to_defaults_restores_defaults(self):
        settings.set_setting('web_port', '9999')
        settings.set_setting('extra', 'junk')
        settings.reset_to_defaults()
        self.assertEqual(settings.get_all_settings(), settings.DEFAULT_SETTINGS)
        self.assertNotIn('extra', settings.get_all_settings())
        with open(settings.SETTINGS_PATH) as f:
            self.assertEqual(json.load(f), settings.DEFAULT_SETTINGS)


if __name__ == '__main__':
    unittest.main(verbosity=2)
