"""Binary upgrade service (§5.6).

Checks GitHub Releases for new versions and downloads matching assets.
"""

import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile

from app.settings import BIN_REPOS, get_bin_dir
from app.process.manager import get_version
from app.logger import log


def check_upgrade(bin_name):
    """Check GitHub for the latest release of *bin_name*.

    Returns:
        dict: {success, current_version, latest_version, download_url, message}
    """
    if bin_name not in BIN_REPOS:
        return {'success': False, 'message': f'Unknown binary: {bin_name}'}

    repo_info = BIN_REPOS[bin_name]
    current_raw = get_version(bin_name)

    # Extract semver from raw output (e.g. "sing-box version 1.13.13" -> "1.13.13")
    m = re.search(r'(\d+\.\d+\.\d+)', current_raw)
    current = m.group(1) if m else current_raw

    # Fetch latest release from GitHub API
    try:
        url = f'https://api.github.com/repos/{repo_info["repo"]}/releases/latest'
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'ProxyHub/1.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = json.loads(resp.read().decode())
    except Exception as e:
        return {'success': False, 'message': f'GitHub API error: {e}'}

    latest_tag = release.get('tag_name', '').lstrip('v')
    latest_version = latest_tag or 'unknown'

    # Find matching asset
    patterns = repo_info['asset_patterns'].get('linux-64', [])
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
        'success':         True,
        'current_version': current,
        'latest_version':  latest_version,
        'download_url':    asset_url,
        'asset_name':      asset_name,
        'is_update':       current != latest_version,
    }


def download_upgrade(bin_name):
    """Download and extract the latest binary for *bin_name*.

    Returns:
        dict: {success, message, version}
    """
    check = check_upgrade(bin_name)
    if not check['success']:
        return check
    if not check['is_update']:
        # Check for missing plugins anyway
        _handle_plugins(bin_name)
        return {'success': True, 'message': 'Already up to date', 'version': check['current_version']}
    if not check['download_url']:
        return {'success': False, 'message': 'No matching asset found for linux-64'}

    log('info', 'upgrade', f'Downloading {bin_name} {check["latest_version"]} ...')

    # Download
    try:
        req = urllib.request.Request(check['download_url'])
        req.add_header('User-Agent', 'ProxyHub/1.0')
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        return {'success': False, 'message': f'Download failed: {e}'}

    # Extract
    bin_dir = get_bin_dir()
    os.makedirs(bin_dir, exist_ok=True)

    asset_name = check['asset_name']
    exe_names = BIN_REPOS[bin_name]['exe_names']

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        if asset_name.endswith('.zip'):
            _extract_zip(tmp_path, bin_dir, exe_names)
        elif asset_name.endswith('.tar.gz') or asset_name.endswith('.tgz'):
            _extract_tar(tmp_path, bin_dir, exe_names, 'gz')
        elif asset_name.endswith('.tar.xz'):
            _extract_tar(tmp_path, bin_dir, exe_names, 'xz')
        else:
            # Single binary
            dest = os.path.join(bin_dir, exe_names[0])
            with open(dest, 'wb') as f:
                f.write(data)
            os.chmod(dest, 0o755)

        os.unlink(tmp_path)
    except Exception as e:
        return {'success': False, 'message': f'Extraction failed: {e}'}

    # Handle plugins
    _handle_plugins(bin_name)

    log('ok', 'upgrade', f'{bin_name} upgraded to {check["latest_version"]}')
    return {'success': True, 'message': f'Upgraded to {check["latest_version"]}',
            'version': check['latest_version']}


def _extract_zip(path, dest_dir, exe_names):
    """Extract matching executables from a .zip archive."""
    with zipfile.ZipFile(path, 'r') as zf:
        for name in zf.namelist():
            basename = os.path.basename(name)
            if basename in exe_names:
                dest = os.path.join(dest_dir, basename)
                with zf.open(name) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(dest, 0o755)


def _extract_tar(path, dest_dir, exe_names, mode):
    """Extract matching executables from a tar archive."""
    fmt = 'r:gz' if mode == 'gz' else 'r:xz'
    with tarfile.open(path, fmt) as tf:
        for member in tf.getmembers():
            basename = os.path.basename(member.name)
            if basename in exe_names and (member.isfile() or member.isreg()):
                dest = os.path.join(dest_dir, basename)
                with tf.extractfile(member) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(dest, 0o755)


def _handle_plugins(bin_name):
    """Handle plugin downloads (obfs-local for sslocal)."""
    repo_info = BIN_REPOS.get(bin_name, {})
    plugins = repo_info.get('plugins', [])
    bin_dir = get_bin_dir()

    for plugin in plugins:
        plugin_name = plugin['name']
        dest = os.path.join(bin_dir, plugin_name)

        if os.path.exists(dest):
            continue  # Already present

        # Check system PATH
        system_path = shutil.which(plugin_name)
        if system_path and os.path.isfile(system_path):
            shutil.copy2(system_path, dest)
            os.chmod(dest, 0o755)
            log('ok', 'upgrade', f'Copied {plugin_name} from {system_path}')
            continue

        log('warn', 'upgrade',
            f'{plugin_name} not found in bin/ or PATH. '
            f'Install with: apt install simple-obfs')
