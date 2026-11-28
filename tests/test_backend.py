import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image

import backend


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = os.path.join(self.directory.name, "workflow.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump({
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
                "9": {"class_type": "SaveImage", "inputs": {}},
            }, file)
        self.env = patch.dict(os.environ, {
            "COMFY_WORKFLOW": path, "COMFY_PROMPT_NODE_ID": "6",
            "COMFY_OUTPUT_NODE_ID": "9", "COMFY_API_KEY": "", "IMAGE_API": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api_key = patch.object(backend, "COMFY_API_KEY", "")
        self.api_key.start()
        self.addCleanup(self.api_key.stop)
        self.image_api = patch.object(backend, "IMAGE_API", "")
        self.image_api.start()
        self.addCleanup(self.image_api.stop)
        self.client = TestClient(backend.app)
        self.addCleanup(self.client.close)
        self.queued_workflow = None

    def png(self, mode="RGBA"):
        output = io.BytesIO()
        Image.new(mode, (2, 2)).save(output, "PNG")
        return output.getvalue()

    def run_pipeline(self, handler):
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch.object(backend.httpx, "AsyncClient", side_effect=lambda **kwargs: original_client(transport=transport, **kwargs)):
            return self.client.post("/generate", json={"prompt": "Schwert", "base_prompt": "centered"})

    def handler(self, request):
        if request.url.path == "/api/chat":
            data = json.loads(request.content)
            self.assertEqual(data["messages"][1]["content"], "Schwert")
            return httpx.Response(200, json={"message": {"content": "pixel art sword"}})
        if request.url.path == "/prompt":
            self.queued_workflow = json.loads(request.content)["prompt"]
            return httpx.Response(200, json={"prompt_id": "job-1"})
        if request.url.path == "/history/job-1":
            return httpx.Response(200, json={"job-1": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {"9": {"images": [{"filename": "asset.png", "subfolder": "test", "type": "output"}]}},
            }})
        if request.url.path == "/view":
            self.assertEqual(request.url.params["subfolder"], "test")
            return httpx.Response(200, content=self.png())
        raise AssertionError(str(request.url))

    def test_pipeline_returns_png_and_replaces_only_positive_prompt(self):
        response = self.run_pipeline(self.handler)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.content, self.png())
        self.assertEqual(self.queued_workflow["6"]["inputs"]["text"], "pixel art sword, centered")
        self.assertEqual(self.queued_workflow["9"]["class_type"], "SaveImage")

    def test_missing_workflow_configuration_is_explicit(self):
        with patch.dict(os.environ, {"COMFY_WORKFLOW": os.path.join(self.directory.name, "missing.json")}):
            response = self.client.post("/generate", json={"prompt": "sword"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("workflow_api.json", response.json()["detail"])

    def test_nodes_are_detected_without_configuration(self):
        workflow = {
            "3": {"class_type": "KSampler", "inputs": {"positive": ["6", 0], "negative": ["7", 0]}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "pos"}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "neg"}},
            "9": {"class_type": "SaveImage", "inputs": {}},
        }
        self.assertEqual(backend.detect_prompt_node(workflow), "6")
        self.assertEqual(backend.detect_output_node(workflow), "9")

    def test_status_reports_unreachable_services(self):
        def handler(request):
            raise httpx.ConnectError("offline", request=request)
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch.object(backend.httpx, "AsyncClient", side_effect=lambda **kwargs: original_client(transport=transport, **kwargs)):
            data = self.client.get("/status").json()
        self.assertEqual(data, {"backend": True, "image_api": "local", "ollama": False, "comfyui": False, "workflow": True})

    def test_private_network_preflight_is_allowed(self):
        response = self.client.options("/generate", headers={
            "Origin": backend.RENDER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        })
        self.assertEqual(response.headers["access-control-allow-origin"], backend.RENDER_ORIGIN)
        self.assertEqual(response.headers["access-control-allow-private-network"], "true")

    def test_blank_prompt_is_rejected(self):
        response = self.client.post("/generate", json={"prompt": "  "})
        self.assertEqual(response.status_code, 422)

    def test_opaque_png_gets_transparent_background(self):
        source = Image.new("RGB", (8, 8), "white")
        source.putpixel((4, 4), (200, 0, 0))
        buffer = io.BytesIO()
        source.save(buffer, "PNG")

        def handler(request):
            if request.url.path == "/view":
                return httpx.Response(200, content=buffer.getvalue())
            return self.handler(request)
        response = self.run_pipeline(handler)
        self.assertEqual(response.status_code, 200)
        result = Image.open(io.BytesIO(response.content))
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((4, 4)), (200, 0, 0, 255))

    def test_comfy_execution_error_is_reported(self):
        def handler(request):
            if request.url.path == "/history/job-1":
                return httpx.Response(200, json={"job-1": {"status": {"status_str": "error", "messages": ["failed"]}}})
            return self.handler(request)
        response = self.run_pipeline(handler)
        self.assertEqual(response.status_code, 502)
        self.assertIn("fehlgeschlagen", response.json()["detail"])

    def test_completed_workflow_without_output_is_reported(self):
        def handler(request):
            if request.url.path == "/history/job-1":
                return httpx.Response(200, json={"job-1": {
                    "status": {"status_str": "success", "completed": True}, "outputs": {},
                }})
            return self.handler(request)
        response = self.run_pipeline(handler)
        self.assertEqual(response.status_code, 502)
        self.assertIn("kein Bild", response.json()["detail"])

    def test_missing_ollama_prompt_is_reported(self):
        def handler(request):
            return httpx.Response(200, json={"message": {"content": ""}})
        response = self.run_pipeline(handler)
        self.assertEqual(response.status_code, 502)
        self.assertIn("keinen Prompt", response.json()["detail"])

    def test_unavailable_service_is_reported(self):
        def handler(request):
            raise httpx.ConnectError("offline", request=request)
        self.assertEqual(self.run_pipeline(handler).status_code, 502)

    def test_health_and_cors(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        response = self.client.options("/generate", headers={
            "Origin": "http://127.0.0.1:5000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:5000")


if __name__ == "__main__":
    unittest.main()
