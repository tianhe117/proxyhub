"""Tests for app/utils/logger.py — the single `log` interface.

Run with:
    python3 -m unittest discover -s test -v

The logger builds one file per process start at import time, in
settings.get_logs_dir(), named YYYY-MM-DD_HHMMSS.log. These tests assert the
public contract: `log` is a stdlib Logger, it writes to a correctly-named
file, and each line records time / level / caller funcName / message.
"""

import logging
import os
import re
import unittest

from app import settings
from app.utils import log


class TestLogInterface(unittest.TestCase):
    """`log` is the single public entry point, shaped as a stdlib Logger."""

    def test_log_is_logger_instance(self):
        self.assertIsInstance(log, logging.Logger)

    def test_log_name_is_proxyhub(self):
        self.assertEqual(log.name, 'proxyhub')

    def test_log_has_single_file_handler(self):
        self.assertEqual(len(log.handlers), 1)
        self.assertIsInstance(log.handlers[0], logging.FileHandler)

    def test_log_level_is_info(self):
        self.assertEqual(log.level, logging.INFO)

    def test_log_does_not_propagate(self):
        # Only writes to file; never bubbles up to root (avoids stderr noise).
        self.assertFalse(log.propagate)


class TestLogFile(unittest.TestCase):
    """The backing file lands in the logs dir with the startup-timestamp name."""

    def _file_path(self):
        return log.handlers[0].baseFilename

    def test_file_is_in_logs_dir(self):
        path = self._file_path()
        self.assertEqual(os.path.dirname(path), settings.get_logs_dir())

    def test_file_name_matches_startup_format(self):
        name = os.path.basename(self._file_path())
        self.assertRegex(name, r'^\d{4}-\d{2}-\d{2}_\d{6}\.log$')

    def test_file_exists_on_disk(self):
        self.assertTrue(os.path.isfile(self._file_path()))


class TestLogWriting(unittest.TestCase):
    """log.info / log.error write formatted lines to the file."""

    def _file_path(self):
        return log.handlers[0].baseFilename

    def _read_lines(self):
        with open(self._file_path(), encoding='utf-8') as f:
            return f.read().splitlines()

    def _last_line(self):
        return self._read_lines()[-1]

    def test_info_writes_formatted_line(self):
        log.info('node switched ok')
        line = self._last_line()
        # [time] [LEVEL] [funcName] message
        self.assertRegex(
            line,
            r'^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] \[INFO\] '
            r'\[test_info_writes_formatted_line\] node switched ok$')

    def test_error_writes_error_level(self):
        log.error('pull failed')
        line = self._last_line()
        self.assertIn(' [ERROR] ', line)
        self.assertTrue(line.endswith('pull failed'))

    def test_funcname_is_caller_function(self):
        # funcName captures the calling test method, not a helper.
        log.warning('check funcName')
        line = self._last_line()
        self.assertIn('[test_funcname_is_caller_function]', line)


if __name__ == '__main__':
    unittest.main(verbosity=2)
