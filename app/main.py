"""FastAPI app que expõe a GUI local da SVBONY SC002.

Run:
    uvicorn app.main:app --reload --port 8765

Variáveis de ambiente:
    SC002_TARGET   - IP da câmera (default 192.168.0.1)
    SC002_TIMEOUT  - timeout HTTP em segundos (default 3)
    SC002_MOCK     - se setado, usa MockCameraClient lendo probe/probe_results.txt
    SC002_FIXTURE  - caminho do probe_results.txt (default probe/probe_results.txt)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .camera_client import (
    DEFAULT_TARGET,
    DEFAULT_TIMEOUT,
    CameraClient,
    MockCameraClient,
    open_in_vlc,
)
from .endpoints import ENDPOINTS, ENDPOINTS_BY_ID, GROUPS

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _build_client() -> Any:
    if os.getenv("SC002_MOCK"):
        fixture = os.getenv("SC002_FIXTURE", str(PROJECT_ROOT / "probe" / "probe_results.txt"))
        return MockCameraClient(fixture, target=os.getenv("SC002_TARGET", DEFAULT_TARGET))
    return CameraClient(
        target=os.getenv("SC002_TARGET", DEFAULT_TARGET),
        timeout=float(os.getenv("SC002_TIMEOUT", DEFAULT_TIMEOUT)),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = _build_client()
    app.state.client = client
    app.state.mock = bool(os.getenv("SC002_MOCK"))
    try:
        yield
    finally:
        await client.close()


app = FastAPI(title="SVBONY SC002 Console", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "target": getattr(request.app.state.client, "target", DEFAULT_TARGET),
            "mock": request.app.state.mock,
        },
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/info")
async def info(request: Request) -> dict[str, Any]:
    client = request.app.state.client
    return {
        "target": getattr(client, "target", DEFAULT_TARGET),
        "mock": request.app.state.mock,
        "groups": list(GROUPS),
        "endpoint_count": len(ENDPOINTS),
    }


@app.get("/api/endpoints")
async def list_endpoints() -> dict[str, Any]:
    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
    by_group["Advanced"] = []  # console raw vive aqui
    for e in ENDPOINTS:
        by_group.setdefault(e.group, []).append(e.to_dict())
    return {"groups": GROUPS + ("Advanced",), "by_group": by_group}


@app.post("/api/call/{endpoint_id}")
async def call_endpoint(
    endpoint_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    endpoint = ENDPOINTS_BY_ID.get(endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=f"endpoint {endpoint_id!r} desconhecido")
    try:
        built = endpoint.build(payload or {})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"build error: {exc}") from exc
    client = request.app.state.client
    result = await client.call(built.method, built.path, list(built.query), endpoint.response_hint)
    return {"endpoint": endpoint.to_dict(), "result": result.to_dict()}


@app.post("/api/raw")
async def call_raw(
    request: Request,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Console livre. Pode disparar QUALQUER request HTTP na câmera.

    Body esperado:
      { "method": "GET", "path": "/cgi-bin/Config.cgi",
        "query": [["action","set"], ["property","Camera.X"], ["value","Y"]] }
    OU:
      { "method": "GET", "url": "http://192.168.0.1/cgi-bin/..." }
    """
    method = (payload.get("method") or "GET").upper()
    client = request.app.state.client
    if "url" in payload and payload["url"]:
        # extrai path+query da URL absoluta
        from urllib.parse import urlparse, parse_qsl
        parsed = urlparse(payload["url"])
        path = parsed.path or "/"
        query = parse_qsl(parsed.query, keep_blank_values=True)
    else:
        path = payload.get("path") or "/"
        query = [(str(k), str(v)) for k, v in (payload.get("query") or [])]
    result = await client.call(method, path, query, payload.get("response_hint", ""))
    return {"result": result.to_dict()}


@app.get("/api/stream-urls")
async def stream_urls(request: Request) -> dict[str, Any]:
    """URLs RTSP. A primeira da lista é a URL CAPTURADA do app oficial via
    honeypot (= a única validada como funcional). As demais são variantes
    descobertas por probe — podem ou não funcionar.
    """
    from urllib.parse import urlparse
    client = request.app.state.client
    target = getattr(client, "target", DEFAULT_TARGET)

    discovered: dict[str, Any] = {}
    suggestions: list[dict[str, str]] = []

    # ★ PRIMEIRA OPÇÃO — exatamente o que o app oficial usa (visto no honeypot)
    suggestions.append({
        "name": "RTSP (app oficial - honeypot)",
        "url": f"rtsp://{target}:554/liveRTSP/av4",
        "note": "URL CAPTURADA do app oficial usando ijkplayer. Esta é a única confirmada como funcional pra streaming real.",
    })

    try:
        res = await client.call("GET", "/app/getmediainfo", response_hint="json")
        if res.parsed_kind == "json" and isinstance(res.parsed, dict):
            info = res.parsed.get("info") or {}
            rtsp_raw = info.get("rtsp") or ""
            port = str(info.get("port") or "")
            transport = info.get("transport") or "tcp"
            discovered = {"rtsp": rtsp_raw, "port": port, "transport": transport}
            if rtsp_raw:
                parsed = urlparse(rtsp_raw)
                path = parsed.path or "/"
                host = parsed.hostname or target
                suggestions.append({
                    "name": "RTSP (declarado em getmediainfo)",
                    "url": rtsp_raw,
                    "note": "URL crua que /app/getmediainfo devolve. Não validada — o app oficial ignora esse path.",
                })
                if port and port != "554":
                    suggestions.append({
                        "name": f"RTSP getmediainfo + porta :{port}",
                        "url": f"rtsp://{host}:{port}{path}",
                        "note": f"transport={transport}",
                    })
    except Exception:  # noqa: BLE001
        pass

    return {"discovered": discovered, "suggestions": suggestions}


@app.post("/api/open-in-vlc")
async def open_vlc(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="url ausente")
    return open_in_vlc(url)


# Path canônico de download (descoberto no probe Fase 3b):
# o lighttpd serve direto em http://CAMERA/{name} onde {name} é o campo
# 'name' devolvido pelo /app/getfilelist (ex: 'EMMC/Photo/F/...jpg').
# Suporta Range requests, Content-Type correto, ETag/Last-Modified.
_DOWNLOAD_TEMPLATE = "/{name}"


def _guess_ct(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".mov"):
        return "video/quicktime"
    return "application/octet-stream"


async def _proxy_static_file(
    request: Request, name: str, *, allow_range: bool
) -> Response:
    """Proxy genérico para arquivos servidos pelo lighttpd da câmera.

    Quando `allow_range=True` (vídeos), repassa o header Range do cliente
    para a câmera — habilita seek nativo no <video> do navegador.
    """
    client = request.app.state.client
    path = "/" + name.lstrip("/")
    # Repassa Range do cliente (se houver) para o servidor da câmera
    extra_headers: dict[str, str] = {}
    if allow_range:
        rng = request.headers.get("range")
        if rng:
            extra_headers["Range"] = rng

    status, headers, content = await client.fetch_bytes_raw(
        path, extra_headers=extra_headers
    )
    if status == 0:
        raise HTTPException(
            status_code=502,
            detail=headers.get("x-error", "fetch failed (camera offline?)"),
        )
    if status == 404:
        raise HTTPException(status_code=404, detail=f"arquivo não encontrado: {name}")

    # Pass-through dos headers úteis (cache, range)
    resp_headers: dict[str, str] = {}
    for h in ("content-range", "accept-ranges", "etag", "last-modified", "content-length"):
        if h in {k.lower() for k in headers.keys()}:
            for k, v in headers.items():
                if k.lower() == h:
                    resp_headers[h] = v
                    break
    ct = headers.get("content-type") or _guess_ct(name)
    return Response(
        content=content,
        media_type=ct,
        status_code=status,
        headers=resp_headers,
    )


@app.get("/api/thumbnail")
async def proxy_thumbnail(request: Request, name: str) -> Response:
    """Thumbnail para arquivos. Para FOTOS (.jpg) devolve a imagem direto
    (são pequenas, 2-3 MB). Para VÍDEOS (.mp4) devolve placeholder neutro,
    já que o /app/getthumbnail real da câmera sempre devolve Content-Length: 0.
    """
    if name.lower().endswith(".mp4"):
        # Placeholder cinza 1x1 (cliente pode usar CSS pra dar aparência de "vídeo")
        png_1x1_gray = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c63986bf26900000004000100c84207c40000000049"
            "454e44ae426082"
        )
        return Response(content=png_1x1_gray, media_type="image/png", status_code=200)
    return await _proxy_static_file(request, name, allow_range=False)


@app.get("/api/file")
async def proxy_file(request: Request, name: str) -> Response:
    """Download/streaming de arquivo. Suporta Range requests do navegador,
    o que faz o <video> conseguir fazer seek nativamente.
    """
    return await _proxy_static_file(request, name, allow_range=True)


@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    client = request.app.state.client
    online = await client.ping()
    return {"online": online, "mock": request.app.state.mock}


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": str(exc), "type": type(exc).__name__}, status_code=500)
