"""Local 2D asset pipeline: Ollama prompt expansion and ComfyUI generation."""

import asyncio
import io
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

app = FastAPI(title="Asset Generator Pipeline")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "UI_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"
    ).split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

SYSTEM_PROMPT = (
    "Convert the user's idea into concise English tags for a single isolated "
    "pixel art game asset. Include a front or isometric view, solid white "
    "background, crisp pixel edges, no anti-aliasing and 16-bit style. "
    "Return only the image prompt, without explanation."
)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    base_prompt: str = Field(default="", max_length=2000)


def load_workflow():
    path = Path(os.getenv("COMFY_WORKFLOW", "workflow_api.json"))
    node_id = os.getenv("COMFY_PROMPT_NODE_ID", "")
    output_id = os.getenv("COMFY_OUTPUT_NODE_ID", "")
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(503, f"ComfyUI-Workflow kann nicht geladen werden: {exc}") from exc
    if not isinstance(workflow, dict) or not node_id or not output_id:
        raise HTTPException(503, "Workflow und COMFY_PROMPT_NODE_ID/COMFY_OUTPUT_NODE_ID konfigurieren.")
    node = workflow.get(node_id)
    if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode" or not isinstance(node.get("inputs"), dict) or not isinstance(node["inputs"].get("text"), str):
        raise HTTPException(503, "Der konfigurierte Prompt-Node muss ein CLIPTextEncode-Node mit Text sein.")
    if not isinstance(workflow.get(output_id), dict):
        raise HTTPException(503, "Der konfigurierte Ausgabe-Node fehlt im Workflow.")
    return workflow, node_id, output_id


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate(request: GenerateRequest):
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(422, "Bitte eine Asset-Idee eingeben.")
    workflow, node_id, output_id = load_workflow()
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    comfy_url = os.getenv("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            answer = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            answer.raise_for_status()
            optimized = answer.json().get("message", {}).get("content", "").strip()
            if not optimized:
                raise HTTPException(502, "Ollama hat keinen Prompt zurückgegeben.")
            workflow[node_id]["inputs"]["text"] = ", ".join(
                part for part in (optimized, request.base_prompt.strip()) if part
            )
            queued = await client.post(f"{comfy_url}/prompt", json={"prompt": workflow})
            queued.raise_for_status()
            prompt_id = queued.json().get("prompt_id")
            if not isinstance(prompt_id, str) or not prompt_id:
                raise HTTPException(502, "ComfyUI hat keine Auftrags-ID zurückgegeben.")

            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                history = await client.get(f"{comfy_url}/history/{prompt_id}")
                history.raise_for_status()
                record = history.json().get(prompt_id)
                if record:
                    status = record.get("status", {})
                    if status.get("status_str") == "error":
                        raise HTTPException(502, f"ComfyUI-Workflow fehlgeschlagen: {status.get('messages', [])}")
                    if status.get("completed"):
                        images = record.get("outputs", {}).get(output_id, {}).get("images", [])
                        if not images:
                            raise HTTPException(502, "Der Ausgabe-Node hat kein Bild erzeugt.")
                        image = images[0]
                        result = await client.get(
                            f"{comfy_url}/view",
                            params={
                                "filename": image["filename"],
                                "subfolder": image.get("subfolder", ""),
                                "type": image.get("type", "output"),
                            },
                        )
                        result.raise_for_status()
                        data = result.content
                        try:
                            with Image.open(io.BytesIO(data)) as png:
                                if png.format != "PNG" or "A" not in png.getbands():
                                    raise HTTPException(502, "Der Workflow muss ein PNG mit Alpha-Kanal ausgeben.")
                                png.load()
                        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                            raise HTTPException(502, "ComfyUI hat kein gültiges PNG zurückgegeben.") from exc
                        return Response(data, media_type="image/png")
                await asyncio.sleep(1)
            raise HTTPException(504, "Zeitüberschreitung beim Warten auf ComfyUI.")
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Zeitüberschreitung bei Ollama oder ComfyUI.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Dienstfehler ({exc.response.status_code}): {exc.response.text[:500]}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Ollama oder ComfyUI ist nicht erreichbar: {exc}") from exc
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(502, "Ungültige Antwort von Ollama oder ComfyUI.") from exc
