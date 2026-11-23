"""Pruebas de blindaje Anti-SSRF, DNS Rebinding e inyección en nombres de modelo."""

from __future__ import annotations

import socket
import unittest
from unittest.mock import patch

from alvea.security.ssrf import SSRFBlockedError, validate_model_id, validate_outbound_url


class TestSSRFProtection(unittest.TestCase):
    def test_allows_local_loopback_on_valid_ports(self) -> None:
        self.assertEqual(
            validate_outbound_url("http://127.0.0.1:11434", mode="local"),
            "http://127.0.0.1:11434",
        )
        self.assertEqual(
            validate_outbound_url("http://localhost:1234/v1", mode="local", resolve_dns=False),
            "http://localhost:1234/v1",
        )

    def test_blocks_cloud_metadata_and_private_networks(self) -> None:
        blocked_urls = [
            ("http://169.254.169.254/latest/meta-data/", "local"),
            ("http://169.254.169.254/latest/meta-data/", "custom"),
            ("https://metadata.google.internal/", "custom"),
            ("http://[::ffff:169.254.169.254]/", "custom"),
            ("http://10.0.0.1:11434", "local"),
            ("https://100.64.0.1/v1", "custom"),  # CGNAT no-global bloqueado
            ("https://192.168.1.10/v1", "custom"),
            ("http://0.0.0.0:11434", "local"),
            ("file:///etc/passwd", "local"),
            ("gopher://127.0.0.1:6379/", "local"),
            ("http://user:pass@127.0.0.1:11434", "local"),
            ("http://127.0.0.1:22", "local"),  # puerto privilegiado < 1024
            ("http://generativelanguage.googleapis.com", "cloud"),  # sin HTTPS
        ]
        for url, mode in blocked_urls:
            with self.subTest(url=url, mode=mode):
                with self.assertRaises(SSRFBlockedError):
                    validate_outbound_url(url, mode=mode, expected_host="generativelanguage.googleapis.com" if mode == "cloud" else None)

    @patch("alvea.security.ssrf.socket.getaddrinfo")
    def test_blocks_dns_rebinding_to_imds(self, mock_getaddrinfo) -> None:
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))
        ]
        with self.assertRaises(SSRFBlockedError):
            validate_outbound_url(
                "https://generativelanguage.googleapis.com",
                mode="cloud",
                expected_host="generativelanguage.googleapis.com",
                resolve_dns=True,
            )

    def test_blocks_model_path_and_query_injection(self) -> None:
        bad_models = [
            "",
            "../../v1/other",
            "gemini-3.8-flash?key=evil",
            "model#fragment",
            "model%2f..%2fadmin",
            "bad\\model",
        ]
        for mid in bad_models:
            with self.subTest(model_id=mid):
                with self.assertRaises(SSRFBlockedError):
                    validate_model_id(mid)

        self.assertEqual(validate_model_id("qwen/qwen3.8-27b:free"), "qwen/qwen3.8-27b:free")
        self.assertEqual(validate_model_id("gemini-3.8-flash"), "gemini-3.8-flash")


if __name__ == "__main__":
    unittest.main()
