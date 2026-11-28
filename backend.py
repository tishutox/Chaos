"""2D asset pipeline: prompt expansion (Gemini or Ollama) and image generation (Cloudflare, Pollinations, or ComfyUI)."""

import asyncio
import base64
import io
import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image, ImageDraw, UnidentifiedImageError
from pydantic import BaseModel, Field

RENDER_ORIGIN = "https://chaos-pt2r.onrender.com"

COMFY_CLOUD_BASE_URL = os.getenv("COMFY_CLOUD_BASE_URL", "https://cloud.comfy.org").rstrip("/")
COMFY_API_KEY = os.getenv("COMFY_API_KEY", "").strip()
IMAGE_API = os.getenv("IMAGE_API", "").strip().lower()
POLLINATIONS_IMAGE_URL = "https://image.pollinations.ai/prompt/{prompt}"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_MODEL = os.getenv("CLOUDFLARE_MODEL", "@cf/black-forest-labs/flux-1-schnell")
CLOUDFLARE_AI_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"

app = FastAPI(title="Asset Generator Pipeline")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "UI_ORIGINS", f"http://localhost:5000,http://127.0.0.1:5000,{RENDER_ORIGIN}"
    ).split(","),
    allow_origin_regex=r"http://(?:localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10(?:\.\d+){3}|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+):5000",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def allow_private_network(request, call_next):
    response = await call_next(request)
    if request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

SYSTEM_PROMPT = (
    "Convert the user's idea into concise English tags for a single isolated "
    "pixel art game asset. Include a front or isometric view, solid white "
    "background, crisp pixel edges, no anti-aliasing and 16-bit style. "
    "Return only the image prompt, without explanation."
)

STYLE_TAGS = (
    "pixel art, 16-bit retro game sprite, crisp hard-edged pixels, flat shading, "
    "clean dark outlines, solid white background, centered, front view, no anti-aliasing"
)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    base_prompt: str = Field(default="", max_length=2000)


def load_workflow():
    path = Path(os.getenv("COMFY_WORKFLOW", "workflow_api.json"))
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(503, f"workflow_api.json fehlt oder ist ungültig ({path}): {exc}") from exc
    if not isinstance(workflow, dict):
        raise HTTPException(503, "Der Workflow muss im ComfyUI-API-Format vorliegen.")
    node_id = os.getenv("COMFY_PROMPT_NODE_ID") or detect_prompt_node(workflow)
    output_id = os.getenv("COMFY_OUTPUT_NODE_ID") or detect_output_node(workflow)
    if not node_id or not output_id:
        raise HTTPException(503, "Prompt- oder Ausgabe-Node nicht gefunden. Workflow prüfen oder COMFY_PROMPT_NODE_ID/COMFY_OUTPUT_NODE_ID setzen.")
    node = workflow.get(node_id)
    if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode" or not isinstance(node.get("inputs"), dict) or not isinstance(node["inputs"].get("text"), str):
        raise HTTPException(503, "Der konfigurierte Prompt-Node muss ein CLIPTextEncode-Node mit Text sein.")
    if not isinstance(workflow.get(output_id), dict):
        raise HTTPException(503, "Der konfigurierte Ausgabe-Node fehlt im Workflow.")
    return workflow, node_id, output_id


def ensure_transparent_png(data):
    """Return a PNG with alpha; flood-fill the solid background from the corners if missing."""
    with Image.open(io.BytesIO(data)) as source:
        if "A" in source.getbands() and source.format == "PNG":
            source.load()
            return data
        image = source.convert("RGBA")
    width, height = image.size
    for corner in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if image.getpixel(corner)[3]:
            ImageDraw.floodfill(image, corner, (0, 0, 0, 0), thresh=48)
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def pixelate_png(data, scale=8):
    """Downscale then upscale with nearest-neighbor to produce crisp pixel edges."""
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGBA")
        width, height = image.size
        small = image.resize((max(1, width // scale), max(1, height // scale)), Image.NEAREST)
        pixelated = small.resize((width, height), Image.NEAREST)
    output = io.BytesIO()
    pixelated.save(output, "PNG")
    return output.getvalue()


def detect_output_node(workflow):
    return next((key for key, node in workflow.items()
                 if isinstance(node, dict) and node.get("class_type") == "SaveImage"), None)


def detect_prompt_node(workflow):
    """Prefer the CLIPTextEncode feeding a sampler's positive input."""
    for node in workflow.values():
        if isinstance(node, dict) and str(node.get("class_type", "")).startswith("KSampler"):
            link = node.get("inputs", {}).get("positive")
            if isinstance(link, list) and link:
                target = workflow.get(str(link[0]))
                if isinstance(target, dict) and target.get("class_type") == "CLIPTextEncode":
                    return str(link[0])
    return next((key for key, node in workflow.items()
                 if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"), None)


async def run_ollama_prompt(client, prompt, ollama_url):
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
    text = answer.json().get("message", {}).get("content", "").strip()
    if not text:
        raise HTTPException(502, "Ollama hat keinen Prompt zurückgegeben.")
    return text


async def run_gemini_prompt(client, prompt):
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
    }
    for attempt in range(3):
        result = await client.post(
            GEMINI_URL.format(model=GEMINI_MODEL),
            headers={"x-goog-api-key": GEMINI_API_KEY},
            json=payload,
        )
        if result.status_code == 503 and attempt < 2:
            await asyncio.sleep(2)
            continue
        result.raise_for_status()
        break
    parts = result.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = " ".join(part.get("text", "").strip() for part in parts if part.get("text")).strip()
    if not text:
        raise HTTPException(502, "Gemini hat keinen Prompt zurückgegeben.")
    return text


async def expand_prompt(client, prompt):
    """Expand the idea via Gemini (cloud); fall back to style tags or local Ollama."""
    if GEMINI_API_KEY:
        try:
            return await run_gemini_prompt(client, prompt)
        except (httpx.HTTPStatusError, httpx.RequestError):
            return f"{prompt}, {STYLE_TAGS}"
    ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    return await run_ollama_prompt(client, prompt, ollama_url)


async def run_cloudflare_image(client, prompt):
    """Generate an image via Cloudflare Workers AI (FLUX/SDXL) and return the raw bytes."""
    result = await client.post(
        CLOUDFLARE_AI_URL.format(account=CLOUDFLARE_ACCOUNT_ID, model=CLOUDFLARE_MODEL),
        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
        json={"prompt": prompt},
    )
    result.raise_for_status()
    image_b64 = (result.json().get("result") or {}).get("image")
    if not image_b64:
        raise HTTPException(502, "Cloudflare hat kein Bild zurückgegeben.")
    return base64.b64decode(image_b64)


async def run_local_comfy(client, workflow, comfy_url, output_id):
    """Queue the workflow on a self-hosted ComfyUI and return the raw PNG bytes."""
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
                return result.content
        await asyncio.sleep(1)
    raise HTTPException(504, "Zeitüberschreitung beim Warten auf ComfyUI.")


async def run_cloud_comfy(client, workflow, cloud_base, api_key):
    """Submit the workflow to Comfy Cloud and return the raw PNG bytes."""
    headers = {"Authorization": f"Bearer {api_key}"}
    submitted = await client.post(f"{cloud_base}/api/v2/jobs", headers=headers, json={"workflow": workflow})
    submitted.raise_for_status()
    job_id = submitted.json().get("id")
    if not isinstance(job_id, str) or not job_id:
        raise HTTPException(502, "Comfy Cloud hat keine Job-ID zurückgegeben.")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        job = await client.get(f"{cloud_base}/api/v2/jobs/{job_id}", headers=headers)
        job.raise_for_status()
        data = job.json()
        status = data.get("status")
        if status in ("failed", "canceled", "expired"):
            detail = (data.get("error") or {}).get("message") or status
            raise HTTPException(502, f"Comfy Cloud-Job fehlgeschlagen: {detail}")
        if status == "succeeded":
            outputs = data.get("outputs") or []
            image = next((o for o in outputs if o.get("type") == "image"), None)
            if not image:
                raise HTTPException(502, "Comfy Cloud hat kein Bild erzeugt.")
            result = await client.get(image["url"])
            result.raise_for_status()
            return result.content
        await asyncio.sleep(2)
    raise HTTPException(504, "Zeitüberschreitung beim Warten auf Comfy Cloud.")


async def run_pollinations(client, prompt, width=512, height=512):
    """Generate an image via the free Pollinations.ai API and return the raw bytes."""
    url = POLLINATIONS_IMAGE_URL.format(prompt=quote(prompt))
    result = await client.get(
        url,
        params={"width": width, "height": height, "model": "flux", "nologo": "true"},
    )
    result.raise_for_status()
    return result.content


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    """Report which of the services are reachable (Cloudflare, Pollinations, or ComfyUI)."""
    if IMAGE_API == "cloudflare":
        mode = "cloudflare"
    elif IMAGE_API == "pollinations":
        mode = "pollinations"
    elif COMFY_API_KEY:
        mode = "comfy_cloud"
    else:
        mode = "local"
    result = {"backend": True, "image_api": mode, "llm_api": "gemini" if GEMINI_API_KEY else "ollama"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
        try:
            result["ollama"] = (await client.get(f"{ollama_url}/api/tags")).is_success
        except httpx.RequestError:
            result["ollama"] = False

        if mode == "comfy_cloud":
            try:
                response = await client.get(
                    f"{COMFY_CLOUD_BASE_URL}/api/v2/jobs?limit=1",
                    headers={"Authorization": f"Bearer {COMFY_API_KEY}"},
                )
                result["comfyui"] = True
                result["cloud_auth"] = response.status_code not in (401, 403)
            except httpx.RequestError:
                result["comfyui"] = False
                result["cloud_auth"] = False
        elif mode == "local":
            comfy_url = os.getenv("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
            try:
                result["comfyui"] = (await client.get(f"{comfy_url}/system_stats")).is_success
            except httpx.RequestError:
                result["comfyui"] = False
    if mode in ("cloudflare", "pollinations"):
        result["workflow"] = None
    else:
        try:
            load_workflow()
            result["workflow"] = True
        except HTTPException:
            result["workflow"] = False
    return result


@app.post("/generate")
async def generate(request: GenerateRequest):
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(422, "Bitte eine Asset-Idee eingeben.")
    use_workflow = IMAGE_API not in ("pollinations", "cloudflare")
    if use_workflow:
        workflow, node_id, output_id = load_workflow()
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            optimized = await expand_prompt(client, prompt)
            final_prompt = ", ".join(
                part for part in (optimized, request.base_prompt.strip()) if part
            )

            if IMAGE_API == "cloudflare":
                try:
                    data = await run_cloudflare_image(client, final_prompt)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 400 and "NSFW" in exc.response.text:
                        data = await run_pollinations(client, final_prompt)
                    else:
                        raise
                try:
                    data = ensure_transparent_png(data)
                    data = pixelate_png(data)
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                    raise HTTPException(502, "Cloudflare hat kein gültiges Bild zurückgegeben.") from exc
            elif IMAGE_API == "pollinations":
                data = await run_pollinations(client, final_prompt)
                try:
                    data = ensure_transparent_png(data)
                    data = pixelate_png(data)
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                    raise HTTPException(502, "Pollinations hat kein gültiges Bild zurückgegeben.") from exc
            else:
                workflow[node_id]["inputs"]["text"] = final_prompt
                if COMFY_API_KEY:
                    data = await run_cloud_comfy(client, workflow, COMFY_CLOUD_BASE_URL, COMFY_API_KEY)
                else:
                    comfy_url = os.getenv("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
                    data = await run_local_comfy(client, workflow, comfy_url, output_id)
                try:
                    data = ensure_transparent_png(data)
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                    raise HTTPException(502, "ComfyUI hat kein gültiges PNG zurückgegeben.") from exc
            return Response(data, media_type="image/png")
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "Zeitüberschreitung beim Prompt- oder Bilddienst.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, f"Dienstfehler ({exc.response.status_code}): {exc.response.text[:500]}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Prompt- oder Bilddienst ist nicht erreichbar: {exc}") from exc
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(502, "Ungültige Antwort vom Prompt- oder Bilddienst.") from exc
