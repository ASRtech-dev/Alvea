"""Pruebas del pipeline IA multi-proveedor, auto-reparación y envío seguro de claves."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from alvea.ai.catalog import get_provider
from alvea.ai.pipeline import ProcessPipeline, repair_and_parse_json_dict
from alvea.ai.providers import call_llm_provider
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


if __name__ == "__main__":
    unittest.main()
