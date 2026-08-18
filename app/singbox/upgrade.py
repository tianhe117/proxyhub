"""sing-box download / upgrade.

Checks GitHub Releases for new sing-box versions and downloads the matching
linux asset. Single engine only — no multi-engine generic, no obfs-local
plugin handling (both dropped in v2).
"""

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile

from app.settings import (
    SINGBOX_REPO,
    SINGBOX_ASSET_PATTERNS,
    SINGBOX_BIN_DIR,
    SINGBOX_BIN_PATH,
    SINGBOX_VERSION_ARGS,
)
from app.utils import log


def get_version() -> str:
    """Return the sing-box version string, or 'N/A' if unavailable."""
    if not os.path.isfile(SINGBOX_BIN_PATH):
        return 'N/A'
    try:
        result = subprocess.run(
            [SINGBOX_BIN_PATH] + SINGBOX_VERSION_ARGS,
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout or result.stderr or ''
        for line in output.splitlines():
            line = line.strip()
            if line:
                return line
        return 'N/A'
    except Exception:
        return 'N/A'


def check_upgrade() -> dict:
    """Check GitHub for the latest sing-box release.

    Returns:
        dict: {success, current_version, latest_version, download_url,
               asset_name, is_update, message}
    """
    current_raw = get_version()

    # "sing-box version 1.13.13" -> "1.13.13"
    m = re.search(r'(\d+\.\d+\.\d+)', current_raw)
    current = m.group(1) if m else current_raw

    try:
        url = f'https://api.github.com/repos/{SINGBOX_REPO}/releases/latest'
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'ProxyHub/1.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode())
    except Exception as e:
        return {'success': False, 'message': f'GitHub API error: {e}'}

    latest_tag = release.get('tag_name', '').lstrip('v')
    latest_version = latest_tag or 'unknown'

    patterns = SINGBOX_ASSET_PATTERNS.get('linux-64', [])
    asset_url = None
    asset_name = None
    for asset in release.get('assets', []):
        name = asset.get('name', '')
        url = asset.get('browser_download_url', '')
        for pat in patterns:
            if pat in name:
                asset_url = url
                asset_name = name
                break
        if asset_url:
            break

    return {
        'success': True,
        'current_version': current,
        'latest_version': latest_version,
        'download_url': asset_url,
        'asset_name': asset_name,
        'is_update': current != latest_version,
    }


def download_upgrade() -> dict:
    """Download and extract the latest sing-box binary to data/bin.

    Returns:
        dict: {success, message, version}
    """
    check = check_upgrade()
    if not check['success']:
        return check
    if not check['is_update']:
        return {'success': True, 'message': 'Already up to date',
                'version': check['current_version']}
    if not check['download_url']:
        return {'success': False, 'message': 'No matching asset found for linux-64'}

    log.info(f'Downloading sing-box {check["latest_version"]} ...')

    try:
        req = urllib.request.Request(check['download_url'])
        req.add_header('User-Agent', 'ProxyHub/1.0')
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        return {'success': False, 'message': f'Download failed: {e}'}

    bin_dir = SINGBOX_BIN_DIR
    os.makedirs(bin_dir, exist_ok=True)
    asset_name = check['asset_name']

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        if asset_name.endswith('.zip'):
            _extract_zip(tmp_path, bin_dir)
        elif asset_name.endswith('.tar.gz') or asset_name.endswith('.tgz'):
            _extract_tar(tmp_path, bin_dir, 'gz')
        elif asset_name.endswith('.tar.xz'):
            _extract_tar(tmp_path, bin_dir, 'xz')
        else:
            # Bare binary
            dest = SINGBOX_BIN_PATH
            with open(dest, 'wb') as f:
                f.write(data)
            os.chmod(dest, 0o755)

        os.unlink(tmp_path)
    except Exception as e:
        return {'success': False, 'message': f'Extraction failed: {e}'}

    log.info(f'sing-box upgraded to {check["latest_version"]}')
    return {'success': True, 'message': f'Upgraded to {check["latest_version"]}',
            'version': check['latest_version']}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_root(name):
    """Drop the first path component of an archive member name.

    sing-box releases bundle files under a top-level version dir
    (e.g. ``sing-box-1.13.13-linux-amd64/sing-box``); stripping it lands
    every file (``sing-box``, ``libcronet.so``, ...) flat into bin_dir.
    """
    parts = name.split('/', 1)
    return parts[1] if len(parts) > 1 else parts[0]


def _extract_zip(path, dest_dir):
    """Extract all members of a .zip archive into *dest_dir* (strip root)."""
    with zipfile.ZipFile(path, 'r') as zf:
        for zi in zf.infolist():
            target = _strip_root(zi.filename)
            if not target or target.endswith('/'):
                continue
            dest = os.path.join(dest_dir, target)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(zi) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            mode = (zi.external_attr >> 16) & 0o777 or 0o644
            os.chmod(dest, mode)


def _extract_tar(path, dest_dir, mode):
    """Extract all members of a tar archive into *dest_dir* (strip root)."""
    fmt = 'r:gz' if mode == 'gz' else 'r:xz'
    with tarfile.open(path, fmt) as tf:
        for member in tf.getmembers():
            target = _strip_root(member.name)
            if not target or member.isdir():
                continue
            dest = os.path.join(dest_dir, target)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with tf.extractfile(member) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(dest, member.mode & 0o777)
