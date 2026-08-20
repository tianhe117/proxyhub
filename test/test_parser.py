#!/usr/bin/env python3
"""Unit tests for app.parser — URI + Clash YAML parsing into node dicts."""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.parser import parse_all
from app.parser import ss, vmess, vless, trojan, hysteria2, tuic
from app.parser.base import decode_base64, filter_lines, parse_kv_params


def _cfg(node):
    """Helper: parse a node's config_json back into a dict."""
    import json
    return json.loads(node['config_json'])


class TestBaseHelpers(unittest.TestCase):

    def test_decode_base64_plain_text_returned_unchanged(self):
        self.assertEqual(decode_base64('not base64 at all'), 'not base64 at all')

    def test_decode_base64_uri_list(self):
        raw = 'dm1lc3M6Ly9leUoxYzJWeUxtRndhUT09'  # base64('vmess://eyJhZGQi...')
        decoded = decode_base64(raw)
        self.assertIn('vmess://', decoded)

    def test_filter_lines_include(self):
        lines = ['ss://x#日本节点', 'ss://y#美国节点', 'ss://z#台湾节点']
        out = filter_lines(lines, include='日本\n台湾', exclude='')
        self.assertEqual(len(out), 2)

    def test_filter_lines_exclude(self):
        lines = ['ss://x#日本节点', 'ss://y#福利节点']
        out = filter_lines(lines, include='', exclude='福利')
        self.assertEqual(len(out), 1)
        self.assertIn('日本', out[0])

    def test_filter_lines_no_keywords(self):
        lines = ['a', 'b', 'c']
        self.assertEqual(filter_lines(lines, '', ''), lines)

    def test_parse_kv_params(self):
        params = parse_kv_params('type=ws&security=tls&sni=example.com')
        self.assertEqual(params['type'], 'ws')
        self.assertEqual(params['security'], 'tls')
        self.assertEqual(params['sni'], 'example.com')


class TestSsParser(unittest.TestCase):

    def test_sip002(self):
        node = ss.parse_uri('ss://YWVzLTI1Ni1nY206cHc=@1.2.3.4:8388#节点1')
        self.assertIsNotNone(node)
        self.assertEqual(node['protocol'], 'ss')
        self.assertEqual(node['address'], '1.2.3.4')
        self.assertEqual(node['port'], 8388)
        self.assertEqual(node['name'], '节点1')
        cfg = _cfg(node)
        self.assertEqual(cfg['method'], 'aes-256-gcm')
        self.assertEqual(cfg['password'], 'pw')

    def test_sip002_with_plugin(self):
        uri = ('ss://YWVzLTEyOC1nY206cHcw@1.2.3.4:8888/'
               '?plugin=obfs-local;obfs=http;obfs-host=host.com#tw')
        node = ss.parse_uri(uri)
        self.assertIsNotNone(node)
        cfg = _cfg(node)
        self.assertEqual(cfg['plugin'], 'obfs-local')
        self.assertIn('obfs=http', cfg['plugin_opts'])

    def test_legacy_full_base64(self):
        # base64('aes-256-gcm:pw@1.2.3.4:8388')
        node = ss.parse_uri('ss://YWVzLTI1Ni1nY206cHdAMS4yLjMuNDo4Mzg4#legacy')
        self.assertIsNotNone(node)
        self.assertEqual(node['address'], '1.2.3.4')
        self.assertEqual(node['port'], 8388)

    def test_bad_input_returns_none(self):
        self.assertIsNone(ss.parse_uri('ss://!!!invalid'))


class TestVmessParser(unittest.TestCase):

    def test_vmess_ws_tls(self):
        # Real-shape vmess base64(json)
        import base64, json
        data = {
            'add': 'example.com', 'port': 443, 'id': 'uuid-123',
            'aid': 0, 'net': 'ws', 'ps': 'vmess-node',
            'host': 'ws.example.com', 'path': '/ray', 'tls': 'tls',
        }
        b64 = base64.b64encode(json.dumps(data).encode()).decode()
        node = vmess.parse_uri(f'vmess://{b64}')
        self.assertIsNotNone(node)
        self.assertEqual(node['protocol'], 'vmess')
        self.assertEqual(node['address'], 'example.com')
        self.assertEqual(node['port'], 443)
        self.assertEqual(node['name'], 'vmess-node')
        cfg = _cfg(node)
        self.assertEqual(cfg['uuid'], 'uuid-123')
        self.assertEqual(cfg['network'], 'ws')
        self.assertTrue(cfg['tls'])
        self.assertEqual(cfg['ws_host'], 'ws.example.com')
        self.assertEqual(cfg['ws_path'], '/ray')

    def test_bad_base64_returns_none(self):
        self.assertIsNone(vmess.parse_uri('vmess://!!!notbase64!!!'))


class TestVlessParser(unittest.TestCase):

    def test_vless_ws(self):
        uri = ('vless://uuid-abc@example.com:443?type=ws&security=tls'
               '&path=/ray&host=example.com&sni=example.com#vless-node')
        node = vless.parse_uri(uri)
        self.assertIsNotNone(node)
        self.assertEqual(node['protocol'], 'vless')
        self.assertEqual(node['address'], 'example.com')
        self.assertEqual(node['port'], 443)
        cfg = _cfg(node)
        self.assertEqual(cfg['uuid'], 'uuid-abc')
        self.assertEqual(cfg['network'], 'ws')
        self.assertTrue(cfg['tls'])
        self.assertEqual(cfg['ws_path'], '/ray')

    def test_vless_tcp_no_tls(self):
        node = vless.parse_uri('vless://uuid@host:443?type=tcp&security=none#n')
        self.assertIsNotNone(node)
        cfg = _cfg(node)
        self.assertFalse(cfg['tls'])


class TestTrojanParser(unittest.TestCase):

    def test_trojan_basic(self):
        uri = 'trojan://secretpw@example.com:443?sni=example.com#trojan-node'
        node = trojan.parse_uri(uri)
        self.assertIsNotNone(node)
        self.assertEqual(node['protocol'], 'trojan')
        self.assertEqual(node['address'], 'example.com')
        self.assertEqual(node['port'], 443)
        cfg = _cfg(node)
        self.assertEqual(cfg['password'], 'secretpw')
        self.assertEqual(cfg['sni'], 'example.com')
        self.assertTrue(cfg['tls'])

    def test_trojan_alpn(self):
        node = trojan.parse_uri('trojan://pw@host:443?alpn=h3,h2#n')
        self.assertIsNotNone(node)
        self.assertEqual(_cfg(node)['alpn'], 'h3,h2')


class TestHysteria2Parser(unittest.TestCase):

    def test_hy2_full(self):
        uri = ('hy2://secretpass@hy2.example.com:443?sni=hy2.example.com'
               '&insecure=1&obfs=salamander&obfs-password=xyz#hy2-node')
        node = hysteria2.parse_uri(uri)
        self.assertIsNotNone(node)
        self.assertEqual(node['protocol'], 'hysteria2')
        self.assertEqual(node['address'], 'hy2.example.com')
        self.assertEqual(node['port'], 443)
        cfg = _cfg(node)
        self.assertEqual(cfg['password'], 'secretpass')
        self.assertTrue(cfg['allowInsecure'])
        self.assertEqual(cfg['obfs'], 'salamander')
        self.assertEqual(cfg['obfs_password'], 'xyz')

    def test_hysteria2_scheme_prefix(self):
        node = hysteria2.parse_uri('hysteria2://pass@host:443?sni=host#h2')
        self.assertIsNotNone(node)
        self.assertEqual(node['protocol'], 'hysteria2')


class TestTuicParser(unittest.TestCase):

    def test_tuic_full(self):
        uri = ('tuic://uuid-abc:password123@tuic.example.com:443'
               '?sni=tuic.example.com&congestion_control=bbr&alpn=h3#tuic-node')
        node = tuic.parse_uri(uri)
        self.assertIsNotNone(node)
        self.assertEqual(node['protocol'], 'tuic')
        self.assertEqual(node['address'], 'tuic.example.com')
        self.assertEqual(node['port'], 443)
        cfg = _cfg(node)
        self.assertEqual(cfg['uuid'], 'uuid-abc')
        self.assertEqual(cfg['password'], 'password123')
        self.assertEqual(cfg['congestion_control'], 'bbr')
        self.assertEqual(cfg['alpn'], 'h3')


class TestParseAll(unittest.TestCase):

    def test_empty_input(self):
        self.assertEqual(parse_all(''), [])
        self.assertEqual(parse_all('   \n  '), [])

    def test_uri_list(self):
        text = (
            'ss://YWVzLTI1Ni1nY206cHc=@1.2.3.4:8388#节点1\n'
            'ss://YWVzLTI1Ni1nY206cHcy@5.6.7.8:8388#节点2\n'
        )
        nodes = parse_all(text)
        self.assertEqual(len(nodes), 2)
        names = [n['name'] for n in nodes]
        self.assertIn('节点1', names)
        self.assertIn('节点2', names)

    def test_dedup_by_name(self):
        text = (
            'ss://YWVzLTI1Ni1nY206cHc=@1.2.3.4:8388#dup\n'
            'ss://YWVzLTI1Ni1nY206cHcy@5.6.7.8:8388#dup\n'
        )
        nodes = parse_all(text)
        self.assertEqual(len(nodes), 1)
        # last occurrence wins
        self.assertEqual(nodes[0]['address'], '5.6.7.8')

    def test_filter_keywords(self):
        text = (
            'ss://YWVzLTI1Ni1nY206cHc=@1.2.3.4:8388#日本节点\n'
            'ss://YWVzLTI1Ni1nY206cHcy@5.6.7.8:8388#美国节点\n'
        )
        nodes = parse_all(text, include='日本', exclude='')
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['name'], '日本节点')

    def test_bad_line_skipped(self):
        text = (
            'ss://!!!invalid\n'
            'ss://YWVzLTI1Ni1nY206cHc=@1.2.3.4:8388#good\n'
        )
        nodes = parse_all(text)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['name'], 'good')

    def test_clash_yaml_detected(self):
        yaml_text = '''mixed-port: 7890
proxies:
- type: ss
  name: yaml-ss
  server: 1.2.3.4
  port: 8388
  cipher: aes-256-gcm
  password: pw
'''
        nodes = parse_all(yaml_text)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['protocol'], 'ss')
        self.assertEqual(nodes[0]['name'], 'yaml-ss')

    def test_unknown_protocol_skipped_in_yaml(self):
        yaml_text = '''proxies:
- type: ssr
  name: ssr-node
  server: 1.2.3.4
  port: 8388
- type: ss
  name: real-ss
  server: 5.6.7.8
  port: 8388
  cipher: aes-256-gcm
  password: pw
'''
        nodes = parse_all(yaml_text)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['name'], 'real-ss')


class TestClashYaml(unittest.TestCase):

    def test_vmess_with_ws_opts(self):
        yaml_text = '''proxies:
- type: vmess
  name: ws-node
  server: example.com
  port: 443
  uuid: uuid-123
  alterId: 0
  cipher: auto
  network: ws
  tls: true
  servername: example.com
  ws-opts:
    path: /ray
    headers:
      Host: ws.example.com
'''
        nodes = parse_all(yaml_text)
        self.assertEqual(len(nodes), 1)
        cfg = _cfg(nodes[0])
        self.assertEqual(cfg['network'], 'ws')
        self.assertEqual(cfg['ws_path'], '/ray')
        self.assertEqual(cfg['ws_host'], 'ws.example.com')

    def test_hysteria2_with_obfs(self):
        yaml_text = '''proxies:
- type: hysteria2
  name: hy2-node
  server: hy2.example.com
  port: 443
  password: secretpass
  sni: hy2.example.com
  alpn:
  - h3
  obfs: salamander
  obfs-password: xyz
'''
        nodes = parse_all(yaml_text)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]['protocol'], 'hysteria2')
        cfg = _cfg(nodes[0])
        self.assertEqual(cfg['obfs'], 'salamander')
        self.assertEqual(cfg['obfs_password'], 'xyz')
        self.assertEqual(cfg['alpn'], 'h3')


if __name__ == '__main__':
    unittest.main()
