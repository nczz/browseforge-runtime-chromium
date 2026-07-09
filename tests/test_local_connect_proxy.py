from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "local_connect_proxy.py"

spec = importlib.util.spec_from_file_location("local_connect_proxy", SCRIPT)
local_connect_proxy = importlib.util.module_from_spec(spec)
sys.modules["local_connect_proxy"] = local_connect_proxy
assert spec.loader is not None
spec.loader.exec_module(local_connect_proxy)


class LocalConnectProxyHelperTests(unittest.TestCase):
    def test_parse_authority_accepts_host_port_and_https_url_authorities(self) -> None:
        cases = (
            ("example.com:443", ("example.com", 443)),
            ("https://example.com:443", ("example.com", 443)),
            ("[2001:db8::1]:8443", ("2001:db8::1", 8443)),
            ("https://[2001:db8::1]:9443", ("2001:db8::1", 9443)),
        )

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(expected, local_connect_proxy.parse_authority(value))

    def test_parse_authority_rejects_missing_or_unsupported_ports_clearly(self) -> None:
        cases = (
            ("example.com", "port"),
            ("https://example.com", "port"),
            ("example.com:not-a-port", "port"),
            ("ftp://example.com:21", "unsupported"),
            ("2001:db8::1:443", "host:port"),
        )

        for value, expected_message in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, expected_message):
                    local_connect_proxy.parse_authority(value)

    def test_sanitize_host_preserves_dns_and_redacts_ips_and_credentials(self) -> None:
        cases = (
            ("example.com", "example.com"),
            ("sub-domain.example.co.uk", "sub-domain.example.co.uk"),
            ("192.0.2.10", "[redacted-ipv4]"),
            ("user:pass@example.com", "[redacted-credential-host]"),
            ("token@example.com", "[redacted-credential-host]"),
        )

        for host, expected in cases:
            with self.subTest(host=host):
                self.assertEqual(expected, local_connect_proxy.sanitize_host(host))

    def test_summarize_events_counts_connects_by_sanitized_host_without_leaking_sensitive_fields(self) -> None:
        events = [
            {
                "method": "CONNECT",
                "authority": "example.com:443",
                "host": "example.com",
                "port": 443,
                "url": "https://example.com/private/path?token=secret",
                "path": "/private/path?token=secret",
                "body": "password=secret",
            },
            {
                "method": "CONNECT",
                "authority": "192.0.2.10:443",
                "host": "192.0.2.10",
                "port": 443,
                "url": "https://192.0.2.10/account",
                "path": "/account",
                "body": "cookie=value",
            },
            {
                "method": "GET",
                "authority": "ignored.example:80",
                "host": "ignored.example",
                "port": 80,
            },
            {
                "method": "CONNECT",
                "authority": "user:pass@example.com:443",
                "host": "user:pass@example.com",
                "port": 443,
                "headers": {"cookie": "session=secret"},
            },
        ]

        summary = local_connect_proxy.summarize_events(events)

        self.assertEqual(3, summary["connect_count"])
        self.assertEqual(
            {
                "example.com": 1,
                "ignored.example": 1,
                "[redacted-ipv4]": 1,
                "[redacted-credential-host]": 1,
            },
            summary["hosts"],
        )
        encoded_summary = repr(summary)
        for sensitive_value in (
            "https://example.com/private/path?token=secret",
            "/private/path?token=secret",
            "password=secret",
            "192.0.2.10",
            "user:pass@example.com",
            "session=secret",
        ):
            with self.subTest(sensitive_value=sensitive_value):
                self.assertNotIn(sensitive_value, encoded_summary)


if __name__ == "__main__":
    unittest.main()
