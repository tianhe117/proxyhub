#!/usr/bin/env python3
"""Unit tests for app.singbox.config — config generation layer."""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.singbox.config import build_config, write_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EMPTY_DB_STATE = {
    'nodes': [],
    'inbounds': [],
    'outbounds': [],
    'outbound_nodes': [],
    'services': [],
}

SAMPLE_DB_STATE = {
    'nodes': [
        {'id': 1, 'protocol': 'ss', 'address': '1.2.3.4', 'port': 8388,
         'config_json': '{"method": "aes-256-gcm", "password": "pw"}'},
        {'id': 2, 'protocol': 'vmess', 'address': '5.6.7.8', 'port': 443,
         'config_json': '{"uuid": "abc", "alterId": 0, "tls": true, "sni": "5.6.7.8"}'},
    ],
    'inbounds': [
        {'id': 10, 'protocol': 'socks', 'listen_addr': '0.0.0.0', 'port': 1080,
         'params_json': '{}'},
        {'id': 11, 'protocol': 'http', 'listen_addr': '0.0.0.0', 'port': 1081,
         'params_json': '{}'},
    ],
    'outbounds': [
        {'id': 0, 'name': 'direct'},
        {'id': 20, 'name': 'my_group'},
    ],
    'outbound_nodes': [
        {'outbound_id': 20, 'node_id': 1, 'priority': 1},
        {'outbound_id': 20, 'node_id': 2, 'priority': 2},
    ],
    'services': [
        {'id': 1, 'name': 'svc1', 'inbound_id': 10, 'outbound_id': 20},
        {'id': 2, 'name': 'svc2', 'inbound_id': 11, 'outbound_id': 0},
    ],
}


class TestBuildConfigEmpty(unittest.TestCase):

    def test_empty_state(self):
        config = build_config(EMPTY_DB_STATE)
        self.assertEqual(config['inbounds'], [])
        # outbounds still has direct + block sentinels
        tags = [ob['tag'] for ob in config['outbounds']]
        self.assertIn('direct', tags)
        self.assertIn('block', tags)
        self.assertEqual(config['route']['rules'], [])
        self.assertEqual(config['route']['final'], 'direct')

    def test_has_log(self):
        config = build_config(EMPTY_DB_STATE)
        self.assertEqual(config['log']['level'], 'info')
        self.assertTrue(config['log']['timestamp'])

    def test_has_experimental(self):
        config = build_config(EMPTY_DB_STATE)
        self.assertIn('clash_api', config['experimental'])


class TestBuildConfigSample(unittest.TestCase):

    def setUp(self):
        self.config = build_config(SAMPLE_DB_STATE)

    def test_inbound_count(self):
        self.assertEqual(len(self.config['inbounds']), 2)

    def test_inbound_tags(self):
        tags = [ib['tag'] for ib in self.config['inbounds']]
        self.assertIn('i10', tags)
        self.assertIn('i11', tags)

    def test_outbound_count(self):
        # 2 nodes + 1 selector + direct + block = 5
        self.assertEqual(len(self.config['outbounds']), 5)

    def test_node_outbounds(self):
        tags = [ob['tag'] for ob in self.config['outbounds']]
        self.assertIn('n1', tags)
        self.assertIn('n2', tags)

    def test_selector(self):
        selectors = [ob for ob in self.config['outbounds'] if ob['type'] == 'selector']
        self.assertEqual(len(selectors), 1)
        sel = selectors[0]
        self.assertEqual(sel['tag'], 'g20')
        self.assertIn('n1', sel['outbounds'])
        self.assertIn('n2', sel['outbounds'])
        self.assertIn('direct', sel['outbounds'])

    def test_route_rules(self):
        rules = self.config['route']['rules']
        self.assertEqual(len(rules), 2)

    def test_route_rule_mapping(self):
        rules = self.config['route']['rules']
        rule_map = {r['inbound'][0]: r['outbound'] for r in rules}
        self.assertEqual(rule_map['i10'], 'g20')  # svc1: inbound 10 → outbound 20
        self.assertEqual(rule_map['i11'], 'direct')  # svc2: inbound 11 → outbound 0

    def test_node_outbound_types(self):
        n1 = next(ob for ob in self.config['outbounds'] if ob['tag'] == 'n1')
        n2 = next(ob for ob in self.config['outbounds'] if ob['tag'] == 'n2')
        self.assertEqual(n1['type'], 'shadowsocks')
        self.assertEqual(n2['type'], 'vmess')


class TestBuildConfigEdgeCases(unittest.TestCase):

    def test_duplicate_inbound_skipped(self):
        state = {
            'nodes': [],
            'inbounds': [{'id': 1, 'protocol': 'socks', 'listen_addr': '0.0.0.0', 'port': 1080, 'params_json': '{}'}],
            'outbounds': [{'id': 0, 'name': 'direct'}],
            'outbound_nodes': [],
            'services': [
                {'id': 1, 'name': 'a', 'inbound_id': 1, 'outbound_id': 0},
                {'id': 2, 'name': 'b', 'inbound_id': 1, 'outbound_id': 0},  # duplicate
            ],
        }
        config = build_config(state)
        self.assertEqual(len(config['route']['rules']), 1)

    def test_missing_inbound_skipped(self):
        state = {
            'nodes': [],
            'inbounds': [],
            'outbounds': [{'id': 0, 'name': 'direct'}],
            'outbound_nodes': [],
            'services': [
                {'id': 1, 'name': 'a', 'inbound_id': 999, 'outbound_id': 0},
            ],
        }
        config = build_config(state)
        self.assertEqual(len(config['route']['rules']), 0)

    def test_missing_outbound_skipped(self):
        state = {
            'nodes': [],
            'inbounds': [{'id': 1, 'protocol': 'socks', 'listen_addr': '0.0.0.0', 'port': 1080, 'params_json': '{}'}],
            'outbounds': [{'id': 0, 'name': 'direct'}],
            'outbound_nodes': [],
            'services': [
                {'id': 1, 'name': 'a', 'inbound_id': 1, 'outbound_id': 999},
            ],
        }
        config = build_config(state)
        self.assertEqual(len(config['route']['rules']), 0)

    def test_empty_pool_selector(self):
        state = {
            'nodes': [],
            'inbounds': [],
            'outbounds': [{'id': 0, 'name': 'direct'}, {'id': 10, 'name': 'empty'}],
            'outbound_nodes': [],
            'services': [],
        }
        config = build_config(state)
        sel = next(ob for ob in config['outbounds'] if ob.get('tag') == 'g10')
        self.assertEqual(sel['outbounds'], ['direct'])


class TestWriteConfig(unittest.TestCase):

    def test_write_and_read(self):
        import json
        config = {'test': True}
        path = write_config(config)
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data, config)
        # cleanup
        os.unlink(path)


if __name__ == '__main__':
    unittest.main()
