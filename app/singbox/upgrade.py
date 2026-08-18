"""sing-box download / upgrade.

Checks GitHub Releases for new sing-box versions and downloads the matching
linux asset. Single engine only — no multi-engine generic, no obfs-local
plugin handling (both dropped in v2).
"""

import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile

from app import settings
from app.singbox import process
from app.utils import log


def check_upgrade() -> dict:
    """Check GitHub for the latest sing-box release.

    Returns:
        dict: {success, current_version, latest_version, download_url,
               asset_name, is_update, message}
    """
    current_raw = process.get_version()

    # "sing-box version 1.13.13" -> "1.13.13"
    m = re.search(r'(\d+\.\d+\.\d+)', current_raw)
    current = m.group(1) if m else current_raw

    try:
        url = f'https://api.github.com/repos/{settings.SINGBOX_REPO}/releases/latest'
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'ProxyHub/1.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode())
    except Exception as e:
        return {'success': False, 'message': f'GitHub API error: {e}'}

    latest_tag = release.get('tag_name', '').lstrip('v')
    latest_version = latest_tag or 'unknown'

    patterns = settings.SINGBOX_ASSET_PATTERNS.get('linux-64', [])
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

    bin_dir = settings.get_bin_dir()
    os.makedirs(bin_dir, exist_ok=True)
    asset_name = check['asset_name']
    exe_name = settings.SINGBOX_EXE

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        if asset_name.endswith('.zip'):
            _extract_zip(tmp_path, bin_dir, exe_name)
        elif asset_name.endswith('.tar.gz') or asset_name.endswith('.tgz'):
            _extract_tar(tmp_path, bin_dir, exe_name, 'gz')
        elif asset_name.endswith('.tar.xz'):
            _extract_tar(tmp_path, bin_dir, exe_name, 'xz')
        else:
            dest = os.path.join(bin_dir, exe_name)
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

def _extract_zip(path, dest_dir, exe_name):
    """Extract the matching executable from a .zip archive."""
    with zipfile.ZipFile(path, 'r') as zf:
        for name in zf.namelist():
            if os.path.basename(name) == exe_name:
                dest = os.path.join(dest_dir, exe_name)
                with zf.open(name) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(dest, 0o755)


def _extract_tar(path, dest_dir, exe_name, mode):
    """Extract the matching executable from a tar archive."""
    fmt = 'r:gz' if mode == 'gz' else 'r:xz'
    with tarfile.open(path, fmt) as tf:
        for member in tf.getmembers():
            if os.path.basename(member.name) == exe_name and (member.isfile() or member.isreg()):
                dest = os.path.join(dest_dir, exe_name)
                with tf.extractfile(member) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(dest, 0o755)
