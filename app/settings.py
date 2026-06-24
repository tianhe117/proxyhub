"""Configuration constants and default values for ProxyHub."""

import os

# ---------------------------------------------------------------------------
# Default settings (§3.2)
# ---------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    'bin_path_xray':        './bin/xray',
    'bin_path_sslocal':     './bin/sslocal',
    'bin_path_singbox':     './bin/sing-box',
    'config_dir':           './config',
    'check_interval_normal': '240',
    'check_interval_failover': '30',
    'tcp_timeout':          '3',
    'curl_timeout':         '5',
    'test_url':             'http://www.gstatic.com/generate_204',
    'web_port':             '8080',
    'web_username':         'admin',
    'web_password':         '',
}

# ---------------------------------------------------------------------------
# Binary registry (§6.1)
# ---------------------------------------------------------------------------
BIN_REGISTRY = {
    'xray': {
        'exe': 'xray',
        'version_args': ['version'],
        'run_args': ['run', '-config', '{config}'],
    },
    'sslocal': {
        'exe': 'sslocal',
        'version_args': ['--version'],
        'run_args': ['-c', '{config}'],
    },
    'sing-box': {
        'exe': 'sing-box',
        'version_args': ['version'],
        'run_args': ['run', '-c', '{config}'],
    },
}

# ---------------------------------------------------------------------------
# GitHub repository configuration (§6.2)
# ---------------------------------------------------------------------------
BIN_REPOS = {
    'xray': {
        'repo': 'XTLS/Xray-core',
        'exe_names': ['xray'],
        'asset_patterns': {'linux-64': ['linux-64', 'linux-x64']},
    },
    'sslocal': {
        'repo': 'shadowsocks/shadowsocks-rust',
        'exe_names': ['sslocal'],
        'asset_patterns': {'linux-64': ['x86_64-unknown-linux']},
        'plugins': [{
            'name': 'obfs-local',
            'repo': 'shadowsocks/simple-obfs',
            'exe_names': ['obfs-local'],
            'asset_patterns': {'linux-64': ['obfs-local']},
        }],
    },
    'sing-box': {
        'repo': 'SagerNet/sing-box',
        'exe_names': ['sing-box'],
        'asset_patterns': {'linux-64': ['linux-amd64', 'linux-x64']},
    },
}

# ---------------------------------------------------------------------------
# Protocol → bin_type mapping (§6.3, §7.6)
# ---------------------------------------------------------------------------
PROTOCOL_BIN_MAP = {
    'vmess':     'xray',
    'vless':     'xray',
    'trojan':    'xray',
    'ssr':       'xray',
    'anytls':    'xray',
    'hysteria':  'sing-box',
    'hysteria2': 'sing-box',
    'tuic':      'sing-box',
}

# ---------------------------------------------------------------------------
# Valid inbound protocols (§6.4)
# ---------------------------------------------------------------------------
VALID_INBOUND_PROTOCOLS = ('http', 'socks', 'ss', 'vmess')

# ---------------------------------------------------------------------------
# Valid bin_types per protocol (for frontend dropdown filtering) (§7.8)
# ---------------------------------------------------------------------------
VALID_BIN_TYPES = {
    'vmess':     ['xray'],
    'vless':     ['xray'],
    'trojan':    ['xray'],
    'ss':        ['xray', 'sslocal'],
    'ssr':       ['xray'],
    'hysteria2': ['sing-box'],
    'tuic':      ['sing-box'],
}

# ---------------------------------------------------------------------------
# SOCKS5 intermediate port range (§15.1)
# ---------------------------------------------------------------------------
SOCKS_PORT_START = 50000
SOCKS_PORT_END   = 60000

# ---------------------------------------------------------------------------
# Runtime path helpers
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_data_dir():
    return os.path.join(BASE_DIR, 'data')

def get_config_dir():
    return os.path.join(BASE_DIR, 'config')

def get_bin_dir():
    return os.path.join(BASE_DIR, 'bin')

def get_db_path():
    return os.path.join(get_data_dir(), 'proxyhub.db')

def get_pid_dir():
    return get_data_dir()
