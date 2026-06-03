from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from huawei_manager.session import NetmikoSession
from huawei_manager.vault import EnvBackend
from huawei_manager.audit_log import AuditLogger


class TestNetmikoSession(unittest.TestCase):

    def setUp(self):
        self.backend = EnvBackend()
        self.audit = AuditLogger()
        self.session = NetmikoSession(self.backend, self.audit)

    def test_init(self):
        self.assertIsNone(self.session._conn)
        self.assertFalse(self.session.is_connected)

    def test_validate_credentials_empty_host_raises(self):
        with patch.object(
            type(self.session), "_host", new_callable=PropertyMock
        ) as mock_host:
            mock_host.return_value = ""
            with self.assertRaises(ValueError) as ctx:
                self.session._validate_credentials()
            self.assertIn("ROUTER_HOST", str(ctx.exception))

    def test_validate_credentials_empty_user_raises(self):
        with patch.object(
            type(self.session), "_user", new_callable=PropertyMock
        ) as mock_user:
            mock_user.return_value = ""
            with self.assertRaises(ValueError) as ctx:
                self.session._validate_credentials()
            self.assertIn("ROUTER_USERNAME", str(ctx.exception))

    def test_validate_credentials_ok(self):
        with (
            patch.object(type(self.session), "_host", new_callable=PropertyMock,
                         return_value="10.0.0.1"),
            patch.object(type(self.session), "_user", new_callable=PropertyMock,
                         return_value="admin"),
            patch.object(type(self.session), "_pass", new_callable=PropertyMock,
                         return_value="secret"),
        ):
            try:
                self.session._validate_credentials()
            except ValueError:
                self.fail("_validate_credentials raised ValueError unexpectedly")

    def test_validate_credentials_no_pass_no_key_raises(self):
        with (
            patch.object(type(self.session), "_host", new_callable=PropertyMock,
                         return_value="10.0.0.1"),
            patch.object(type(self.session), "_user", new_callable=PropertyMock,
                         return_value="admin"),
            patch.object(type(self.session), "_pass", new_callable=PropertyMock,
                         return_value=""),
            patch.object(type(self.session), "_ssh_key", new_callable=PropertyMock,
                         return_value=None),
        ):
            with self.assertRaises(ValueError) as ctx:
                self.session._validate_credentials()
            self.assertIn("ROUTER_PASSWORD", str(ctx.exception))

    def test_resolve_filter_full_config(self):
        result = NetmikoSession._resolve_filter("full_config")
        self.assertEqual(result, "display current-configuration")

    def test_resolve_filter_routing(self):
        result = NetmikoSession._resolve_filter("routing")
        self.assertEqual(result, "display ip routing-table")

    def test_resolve_filter_arp(self):
        result = NetmikoSession._resolve_filter("arp")
        self.assertEqual(result, "display arp")

    def test_resolve_filter_none(self):
        self.assertIsNone(NetmikoSession._resolve_filter(None))

    def test_resolve_filter_unknown(self):
        self.assertIsNone(NetmikoSession._resolve_filter("unknown_filter"))

    def test_session_id_without_conn(self):
        self.assertIsNone(self.session._session_id)


if __name__ == "__main__":
    unittest.main()
