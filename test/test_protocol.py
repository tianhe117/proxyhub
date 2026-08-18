#!/usr/bin/env python3
"""Unit tests for app.singbox.protocol — protocol mapping layer."""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.singbox.protocol import (
    build_outbound,
    build_inbound,
    _parse_json,
)


class TestParseJson(unittest.TestCase):

    def test_none(self):
        self.assertEqual(_parse_json(None), {})

    def test_dict_passthrough(self):
        d = {'a': 1}
        self.assertEqual(_parse_json(d), d)

    def test_valid_string(self):
        self.assertEqual(_parse_json('{"a": 1}'), {'a': 1})

    def test_invalid_string(self):
        self.assertEqual(_parse_json('not json'), {})

    def test_non_dict_json(self):
        self.assertEqual(_parse_json('[1, 2]'), {})


class TestBuildOutbound(unittest.TestCase):

    def test_direct(self):
        ob = build_outbound('direct', '', 0, 'direct', None)
        self.assertEqual(ob, {'type': 'direct', 'tag': 'direct'})

    def test_ss(self):
        ob = build_outbound('n1', '1.2.3.4', 8388, 'ss',
                            '{"method": "aes-256-gcm", "password": "pw"}')
        self.assertEqual(ob['type'], 'shadowsocks')
        self.assertEqual(ob['tag'], 'n1')
        self.assertEqual(ob['server'], '1.2.3.4')
        self.assertEqual(ob['server_port'], 8388)
        self.assertEqual(ob['method'], 'aes-256-gcm')
        self.assertEqual(ob['password'], 'pw')
        self.assertEqual(ob['plugin'], '')
        self.assertEqual(ob['plugin_opts'], '')

    def test_ss_with_obfs(self):
        ob = build_outbound('n1', '1.2.3.4', 8388, 'ss',
                            '{"method": "aes-128-gcm", "password": "pw", "plugin": "obfs-local", "plugin_opts": "obfs=http;obfs-host=test.com"}')
        self.assertEqual(ob['plugin'], 'obfs-local')
        self.assertEqual(ob['plugin_opts'], 'obfs=http;obfs-host=test.com')

    def test_vmess(self):
        ob = build_outbound('n2', 'srv.com', 443, 'vmess',
                            '{"uuid": "abc", "alterId": 0, "security": "auto", "tls": true, "sni": "srv.com"}')
        self.assertEqual(ob['type'], 'vmess')
        self.assertEqual(ob['uuid'], 'abc')
        self.assertEqual(ob['alter_id'], 0)
        self.assertIn('tls', ob)

    def test_vless(self):
        ob = build_outbound('n3', 'srv.com', 443, 'vless',
                            '{"uuid": "x", "tls": true, "sni": "srv.com", "network": "ws", "ws_path": "/p"}')
        self.assertEqual(ob['type'], 'vless')
        self.assertIn('tls', ob)
        self.assertIn('transport', ob)

    def test_trojan(self):
        ob = build_outbound('n4', 'srv.com', 443, 'trojan',
                            '{"password": "pw", "tls": true, "sni": "srv.com"}')
        self.assertEqual(ob['type'], 'trojan')
        self.assertEqual(ob['password'], 'pw')

    def test_hysteria2(self):
        ob = build_outbound('n5', 'srv.com', 443, 'hysteria2',
                            '{"password": "pw", "sni": "srv.com"}')
        self.assertEqual(ob['type'], 'hysteria2')
        self.assertEqual(ob['password'], 'pw')
        self.assertIn('tls', ob)

    def test_tuic(self):
        ob = build_outbound('n6', 'srv.com', 443, 'tuic',
                            '{"uuid": "u", "password": "p", "sni": "srv.com"}')
        self.assertEqual(ob['type'], 'tuic')
        self.assertEqual(ob['uuid'], 'u')

    def test_unsupported_raises(self):
        with self.assertRaises(ValueError):
            build_outbound('n99', 'x', 1, 'ssr', '{}')

    def test_string_config(self):
        ob = build_outbound('n1', '1.2.3.4', 8388, 'ss',
                            '{"method": "chacha20", "password": "pw"}')
        self.assertEqual(ob['method'], 'chacha20')

    def test_dict_config(self):
        ob = build_outbound('n1', '1.2.3.4', 8388, 'ss',
                            {'method': 'chacha20', 'password': 'pw'})
        self.assertEqual(ob['method'], 'chacha20')

    def test_port_string_coercion(self):
        ob = build_outbound('n1', '1.2.3.4', '8388', 'ss',
                            '{"method": "aes-256-gcm", "password": "pw"}')
        self.assertEqual(ob['server_port'], 8388)
        self.assertIsInstance(ob['server_port'], int)


class TestBuildInbound(unittest.TestCase):

    def test_http(self):
        ib = build_inbound('i1', 'http', '0.0.0.0', 8081,
                           '{"username": "u", "password": "p"}')
        self.assertEqual(ib['type'], 'http')
        self.assertEqual(ib['tag'], 'i1')
        self.assertEqual(ib['users'], [{'username': 'u', 'password': 'p'}])

    def test_http_no_auth(self):
        ib = build_inbound('i1', 'http', '0.0.0.0', 8081,
                           '{"username": "", "password": ""}')
        self.assertNotIn('users', ib)

    def test_socks(self):
        ib = build_inbound('i2', 'socks', '0.0.0.0', 1080, '{}')
        self.assertEqual(ib['type'], 'socks')
        self.assertNotIn('users', ib)

    def test_ss(self):
        ib = build_inbound('i3', 'ss', '0.0.0.0', 8388,
                           '{"method": "aes-256-gcm", "password": "pw"}')
        self.assertEqual(ib['type'], 'shadowsocks')
        self.assertEqual(ib['method'], 'aes-256-gcm')

    def test_vmess(self):
        ib = build_inbound('i4', 'vmess', '0.0.0.0', 24811,
                           '{"uuid": "abc", "alterId": 64}')
        self.assertEqual(ib['type'], 'vmess')
        self.assertEqual(ib['users'][0]['uuid'], 'abc')
        self.assertEqual(ib['users'][0]['alterId'], 64)

    def test_unsupported_raises(self):
        with self.assertRaises(ValueError):
            build_inbound('i99', 'hysteria2', '0.0.0.0', 1, '{}')

    def test_default_listen(self):
        ib = build_inbound('i1', 'http', None, 8081, '{}')
        self.assertEqual(ib['listen'], '0.0.0.0')


if __name__ == '__main__':
    unittest.main()
