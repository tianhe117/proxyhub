"""Direct smoke test for app/singbox/upgrade.py public interfaces.

No test framework is used. Run directly from anywhere:

    python test/test_upgrade.py

It calls the three public interfaces in order and prints their return
values. Note that download_upgrade() may download and replace the local
sing-box binary if a newer release is available.
"""

import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.singbox.upgrade import check_upgrade, download_upgrade, get_version


def _show(title, value):
    print(f'===== {title} =====')
    if isinstance(value, dict):
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print(value)
    print()


def main():
    _show('get_version()', get_version())
    _show('check_upgrade()', check_upgrade())
    _show('download_upgrade()', download_upgrade())


if __name__ == '__main__':
    main()
