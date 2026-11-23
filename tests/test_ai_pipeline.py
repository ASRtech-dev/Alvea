"""Pruebas del pipeline IA multi-proveedor, auto-reparación y envío seguro de claves."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from alvea.ai.catalog import get_provider
from alvea.ai.pipeline import ProcessPipeline, repair_and_parse_json_dict
from alvea.ai.providers import ProviderCallError, call_llm_provider, test_provider_connection
from alvea.models import Direction, ProcessGraph


class TestAIPipeline(unittest.TestCase):
    def test_local_json_sanitizer_handles_think_tags_trailing_commas_and_aliases(self) -> None:
        noisy_llm_output = """<think>Analizando carriles y nodos...</think>
        ```json
        {
          "process_name": "Alta de Proveedor",
          "swimlanes": [
            {"id": "L_COM", "name": "Compras", "role_type": "department"},
            {"id": "L_ERP", "name": "ERP", "role_type": "system"},
          ],
          "steps": [
            {"id": "N1", "lane_id": "L_COM", "label": "True Positive Check", "node_type": "start"},
            {"id": "N2", "lane_id": "L_ERP", "label": "Activar código", "node_type": "end", "automation_level": "automated"},
          ],
          "transitions": [
            {"from": "N1", "to": "N2", "is_rework_loop": False},
          ],
          "executive_summary": "Proceso automatizado de alta.",
        }
        ```"""
        parsed = repair_and_parse_json_dict(noisy_llm_output)
        graph = ProcessGraph.model_validate(parsed)
        self.assertEqual(graph.title, "Alta de Proveedor")
        self.assertEqual(graph.nodes[0].label, "True Positive Check")
        self.assertEqual(len(graph.lanes), 2)
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(len(graph.edges), 1)
        self.assertTrue(graph.nodes[1].is_automated)

    @patch("alvea.ai.pipeline.call_llm_provider")
    def test_mermaid_fallback_when_small_model_ignores_json(self, mock_call: MagicMock) -> None:
        mock_call.return_value = (
            """```mermaid
            graph LR
            subgraph CLI["Cliente"]
                C1(["Inicio: Enviar pedido"])
                C2(["Fin: Pedido recibido"])
            end
            C1 --> C2
            ```""",
            {},
        )
        pipeline = ProcessPipeline()
        outcome = pipeline.generate(
            text="Cliente envía pedido y recibe confirmación.",
            provider_id="ollama",
            model_id="llama3.2:3b",
            direction=Direction.LR,
        )
        self.assertEqual(outcome.meta["stage"], "mermaid_fallback")
        self.assertGreaterEqual(len(outcome.graph.nodes), 2)
        self.assertIn("graph LR", outcome.mermaid)

    @patch("alvea.ai.providers.validate_outbound_url", side_effect=lambda u, **kw: u)
    @patch("alvea.ai.providers.httpx.Client")
    def test_gemini_sends_key_in_header_never_in_query_string(
        self, mock_client_cls: MagicMock, _mock_ssrf: MagicMock
    ) -> None:
        sentinel_key = "AIzaSyTEST_SENTINEL_HEADER_ONLY_9999"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_bytes.return_value = [b'{"candidates":[{"content":{"parts":[{"text":"{\\"ok\\":true}"}]}}]}']

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = get_provider("gemini")
        assert provider is not None
        call_llm_provider(
            provider=provider,
            model_id="gemini-3.8-flash",
            system_prompt="sys",
            user_prompt="usr",
            json_schema={},
            mode="json_object",
            api_key=sentinel_key,
        )

        call_args = mock_client.stream.call_args
        called_method, called_url = call_args.args[0], call_args.args[1]
        called_headers = call_args.kwargs["headers"]

        self.assertEqual(called_method, "POST")
        self.assertNotIn("key=", called_url)
        self.assertNotIn(sentinel_key, called_url)
        self.assertEqual(called_headers.get("x-goog-api-key"), sentinel_key)

    @patch("alvea.ai.providers.validate_outbound_url", side_effect=lambda u, **kw: u)
    @patch("alvea.ai.providers.httpx.Client")
    def test_custom_protocol_anthropic_and_custom_auth_header(
        self, mock_client_cls: MagicMock, _mock_ssrf: MagicMock
    ) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_bytes.return_value = [b'{"content":[{"type":"text","text":"OK"}]}']

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = get_provider("custom_openai")
        assert provider is not None
        text, _ = call_llm_provider(
            provider=provider,
            model_id="claude-custom-1",
            system_prompt="sys",
            user_prompt="usr",
            json_schema={},
            mode="prompt_only",
            api_key="my_custom_secret_token_999",
            custom_base_url="https://api.example-gateway.com",
            custom_protocol="anthropic",
            custom_auth_header="X-Gateway-Key",
            custom_auth_prefix="Token",
        )
        self.assertEqual(text, "OK")
        call_args = mock_client.stream.call_args
        self.assertEqual(call_args.args[1], "https://api.example-gateway.com/v1/messages")
        self.assertEqual(call_args.kwargs["headers"].get("X-Gateway-Key"), "Token my_custom_secret_token_999")

    @patch("alvea.ai.providers.validate_outbound_url", side_effect=lambda u, **kw: u)
    @patch("alvea.ai.providers.httpx.Client")
    def test_gemini_connection_probe_uses_models_endpoint_and_syncs_models(
        self, mock_client_cls: MagicMock, _mock_ssrf: MagicMock
    ) -> None:
        sentinel_key = "AIzaSyGEMINI_PROBE_TEST_999999"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_bytes.return_value = [
            (
                b'{"models":['
                b'{"name":"models/gemini-2.5-flash","displayName":"Gemini 2.5 Flash","supportedGenerationMethods":["generateContent"]},'
                b'{"name":"models/gemini-3.1-flash-lite","displayName":"Gemini 3.1 Flash-Lite","supportedGenerationMethods":["generateContent"]},'
                b'{"name":"models/text-embedding-004","displayName":"Embedding","supportedGenerationMethods":["embedContent"]}'
                b"]}"
            )
        ]

        mock_client = MagicMock()
        mock_client.stream.return_value.__enter__.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        result = test_provider_connection(provider_id="gemini", api_key=sentinel_key)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(len(result["models"]), 2)
        self.assertEqual(result["models"][0]["id"], "gemini-2.5-flash")

        call_args = mock_client.stream.call_args
        self.assertEqual(call_args.args[0], "GET")
        self.assertEqual(call_args.args[1], "https://generativelanguage.googleapis.com/v1beta/models")
        self.assertNotIn(sentinel_key, call_args.args[1])
        self.assertEqual(call_args.kwargs["headers"].get("x-goog-api-key"), sentinel_key)

    @patch("alvea.ai.providers.time.sleep")
    @patch("alvea.ai.providers.validate_outbound_url", side_effect=lambda u, **kw: u)
    @patch("alvea.ai.providers.httpx.Client")
    def test_gemini_retries_once_on_503_overload(
        self, mock_client_cls: MagicMock, _mock_ssrf: MagicMock, _mock_sleep: MagicMock
    ) -> None:
        resp_503 = MagicMock()
        resp_503.status_code = 503
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.iter_bytes.return_value = [b'{"candidates":[{"content":{"parts":[{"text":"{\\"ok\\":true}"}]}}]}']

        cm_503 = MagicMock()
        cm_503.__enter__.return_value = resp_503
        cm_200 = MagicMock()
        cm_200.__enter__.return_value = resp_200

        mock_client = MagicMock()
        mock_client.stream.side_effect = [cm_503, cm_200]
        mock_client_cls.return_value.__enter__.return_value = mock_client

        provider = get_provider("gemini")
        assert provider is not None
        text, _ = call_llm_provider(
            provider=provider,
            model_id="gemini-2.5-flash-lite",
            system_prompt="sys",
            user_prompt="usr",
            json_schema={},
            mode="json_object",
            api_key="AIzaSyRETRY_503_TEST_9999999",
        )
        self.assertEqual(text, '{"ok":true}')
        self.assertEqual(mock_client.stream.call_count, 2)


if __name__ == "__main__":
    unittest.main()
