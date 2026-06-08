"""Cliente HTTP para a SVBONY SC002.

Encapsula:
  - headers exatos do app oficial (HSMSCAM2/1.9.1)
  - timeout curto (rede local)
  - parser dual KEY=VALUE / JSON
  - geração do curl equivalente para a UI exibir
  - modo MOCK que serve respostas canned de probe_results.txt

Sem estado entre chamadas. Thread-safe via httpx.AsyncClient.
"""
from __future__ import annotations

import asyncio
import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

DEFAULT_TARGET = "192.168.0.1"
DEFAULT_TIMEOUT = 3.0
DEFAULT_UA = "HSMSCAM2/1.9.1 (iPad; iOS 26.6; Scale/2.00)"


def default_headers(target: str) -> dict[str, str]:
    return {
        "Host": target,
        "Accept": "*/*",
        "Accept-Language": "pt-BR;q=1, en-BR;q=0.9, es-419;q=0.8",
        "Connection": "keep-alive",
        "Accept-Encoding": "identity",
        "User-Agent": DEFAULT_UA,
    }


@dataclass
class CallResult:
    method: str
    url: str
    status: int
    headers: dict[str, str]
    body_text: str
    elapsed_ms: int
    parsed: Any = None
    parsed_kind: str = "raw"  # "json" | "key_value" | "html" | "raw" | "error"
    error: str | None = None
    curl_equivalent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "status": self.status,
            "headers": self.headers,
            "body_text": self.body_text,
            "elapsed_ms": self.elapsed_ms,
            "parsed": self.parsed,
            "parsed_kind": self.parsed_kind,
            "error": self.error,
            "curl_equivalent": self.curl_equivalent,
        }


def parse_body(body: str, content_type: str, hint: str = "") -> tuple[Any, str]:
    """Devolve (parsed, kind)."""
    body = body.lstrip("\ufeff").strip()
    if not body:
        return None, "raw"

    if hint == "json" or "json" in content_type.lower():
        try:
            return json.loads(body), "json"
        except json.JSONDecodeError:
            # alguns endpoints "json" devolvem texto puro em erro
            pass

    # Tenta JSON mesmo sem hint (vários /app/* respondem application/text mas com JSON)
    if body[0] in "{[":
        try:
            return json.loads(body), "json"
        except json.JSONDecodeError:
            pass

    # Detecta KEY=VALUE em múltiplas linhas (Config.cgi / hisnet pattern).
    # Pode ter cabeçalho "0\nOK\n" e rodapé "0\nOK\n" (chunked).
    lines = [ln for ln in body.splitlines() if ln.strip()]
    kv: dict[str, Any] = {}
    other: list[str] = []
    for ln in lines:
        if ln.strip() in {"0", "OK"}:
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9_.\-]*)=(.*)$", ln)
        if m:
            kv[m.group(1)] = m.group(2)
        else:
            other.append(ln)
    if kv:
        return {"pairs": kv, "extra": other}, "key_value"

    if body.lstrip().startswith("<"):
        return body, "html"

    return body, "raw"


def build_curl(method: str, url: str, headers: dict[str, str]) -> str:
    parts: list[str] = ["curl", "-sS", "-i", "--http1.1", "-X", method]
    for k, v in headers.items():
        parts.append("-H")
        parts.append(f"{k}: {v}")
    parts.append(url)
    return " ".join(shlex.quote(p) for p in parts)


class CameraClient:
    """Cliente real (HTTP)."""

    def __init__(self, target: str = DEFAULT_TARGET, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.target = target
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout),
                    headers=default_headers(self.target),
                    http2=False,
                    trust_env=False,
                )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def base_url(self) -> str:
        return f"http://{self.target}"

    async def call(
        self,
        method: str,
        path: str,
        query: list[tuple[str, str]] | None = None,
        response_hint: str = "",
    ) -> CallResult:
        # IMPORTANTE: o firmware aceita '$' literal na query. urlencode escapa por
        # padrão; precisamos manter '$.*' fora do encoding.
        qstr = urlencode(query, safe="$.*") if query else ""
        url = f"{self.base_url}{path}"
        if qstr:
            url = f"{url}?{qstr}"

        client = await self._get_client()
        started = time.monotonic()
        try:
            response = await client.request(method.upper(), url)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            ct = response.headers.get("content-type", "")
            body = response.text
            parsed, kind = parse_body(body, ct, response_hint)
            return CallResult(
                method=method.upper(),
                url=url,
                status=response.status_code,
                headers=dict(response.headers),
                body_text=body,
                elapsed_ms=elapsed_ms,
                parsed=parsed,
                parsed_kind=kind,
                curl_equivalent=build_curl(method.upper(), url, default_headers(self.target)),
            )
        except httpx.TimeoutException as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return CallResult(
                method=method.upper(),
                url=url,
                status=0,
                headers={},
                body_text="",
                elapsed_ms=elapsed_ms,
                error=f"timeout: {exc}",
                parsed_kind="error",
                curl_equivalent=build_curl(method.upper(), url, default_headers(self.target)),
            )
        except httpx.HTTPError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return CallResult(
                method=method.upper(),
                url=url,
                status=0,
                headers={},
                body_text="",
                elapsed_ms=elapsed_ms,
                error=f"http_error: {exc}",
                parsed_kind="error",
                curl_equivalent=build_curl(method.upper(), url, default_headers(self.target)),
            )

    async def ping(self) -> bool:
        """Heartbeat barato. /app/getbatteryinfo é leve, sempre disponível,
        e não tem efeito colateral. (Antes usava hisnet/* que dá 404 nesta câmera.)
        """
        res = await self.call("GET", "/app/getbatteryinfo")
        return res.error is None and 200 <= res.status < 500

    async def fetch_bytes(
        self,
        path: str,
        query: list[tuple[str, str]] | None = None,
        method: str = "GET",
    ) -> tuple[int, dict[str, str], bytes]:
        """Versão de `call` que retorna body BINÁRIO (para JPEG/MP4).
        Usada por /api/thumbnail e /api/file proxies. Sem parsing.
        """
        qstr = urlencode(query, safe="$.*") if query else ""
        url = f"{self.base_url}{path}"
        if qstr:
            url = f"{url}?{qstr}"
        client = await self._get_client()
        try:
            response = await client.request(method.upper(), url)
            return response.status_code, dict(response.headers), response.content
        except httpx.HTTPError as exc:
            return 0, {"x-error": str(exc)}, b""

    async def fetch_bytes_raw(
        self,
        path: str,
        extra_headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> tuple[int, dict[str, str], bytes]:
        """Como fetch_bytes mas usa o path EXATAMENTE como recebido (sem
        urlencode) e passa headers extras (Range, etc.). Necessário para
        servir arquivos por path como /EMMC/Photo/F/20260607182633.jpg.
        """
        url = f"{self.base_url}{path}"
        client = await self._get_client()
        merged_headers = None
        if extra_headers:
            # httpx faz merge automático com os headers default do client
            merged_headers = extra_headers
        try:
            response = await client.request(
                method.upper(), url, headers=merged_headers
            )
            return response.status_code, dict(response.headers), response.content
        except httpx.HTTPError as exc:
            return 0, {"x-error": str(exc)}, b""


# ============================================================================
# Mock client — serve dados canned a partir de probe_results.txt ou fixtures
# ============================================================================

_PROBE_BLOCK_RE = re.compile(
    r"=== \[(?P<group>[^\]]+)\] (?P<method>GET|POST|HEAD|TCP) (?P<url>.+?) ===\n"
    r"(?P<body>.*?)\n=== END",
    re.DOTALL,
)


def _strip_http_headers(body: str) -> tuple[int, dict[str, str], str]:
    """De um bloco 'HTTP/1.1 200 OK\\n...\\n\\nBODY' tira o que importa."""
    if not body.startswith(("HTTP/", "OPEN", "CLOSED")):
        return 0, {}, body.strip()
    if body.startswith(("OPEN", "CLOSED")):
        return 0, {}, body.strip()
    lines = body.split("\n")
    status_line = lines[0]
    m = re.match(r"HTTP/[\d.]+\s+(\d+)", status_line)
    status = int(m.group(1)) if m else 0
    headers: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i].strip():
        if ":" in lines[i]:
            k, _, v = lines[i].partition(":")
            headers[k.strip().lower()] = v.strip()
        i += 1
    body_text = "\n".join(lines[i + 1 :]).strip()
    return status, headers, body_text


class MockCameraClient:
    """Replica a interface do CameraClient lendo de probe_results.txt."""

    def __init__(self, fixture_path: str, target: str = DEFAULT_TARGET) -> None:
        self.target = target
        self._fixture: dict[str, tuple[int, dict[str, str], str]] = {}
        self._load(fixture_path)

    @property
    def base_url(self) -> str:
        return f"http://{self.target}"

    def _load(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except FileNotFoundError:
            return
        for m in _PROBE_BLOCK_RE.finditer(text):
            url = m.group("url").strip()
            method = m.group("method").strip()
            status, headers, body = _strip_http_headers(m.group("body"))
            key = f"{method} {url}"
            self._fixture[key] = (status, headers, body)

    async def call(
        self,
        method: str,
        path: str,
        query: list[tuple[str, str]] | None = None,
        response_hint: str = "",
    ) -> CallResult:
        qstr = urlencode(query, safe="$.*") if query else ""
        url = f"{self.base_url}{path}"
        if qstr:
            url = f"{url}?{qstr}"
        key = f"{method.upper()} {url}"
        fix = self._fixture.get(key)
        if fix is None:
            # Tenta sem trailing "?" que algumas chamadas têm
            alt = key.rstrip("?")
            fix = self._fixture.get(alt)
        if fix is None:
            return CallResult(
                method=method.upper(),
                url=url,
                status=0,
                headers={},
                body_text="",
                elapsed_ms=0,
                parsed_kind="error",
                error=f"mock: no fixture for {key}",
                curl_equivalent=build_curl(method.upper(), url, default_headers(self.target)),
            )
        status, headers, body = fix
        ct = headers.get("content-type", "")
        parsed, kind = parse_body(body, ct, response_hint)
        return CallResult(
            method=method.upper(),
            url=url,
            status=status,
            headers=headers,
            body_text=body,
            elapsed_ms=1,
            parsed=parsed,
            parsed_kind=kind,
            curl_equivalent=build_curl(method.upper(), url, default_headers(self.target)),
        )

    async def ping(self) -> bool:
        res = await self.call("GET", "/app/getbatteryinfo")
        return res.status != 0

    async def fetch_bytes(
        self,
        path: str,
        query: list[tuple[str, str]] | None = None,
        method: str = "GET",
    ) -> tuple[int, dict[str, str], bytes]:
        # Mock só serve placeholder PNG 1x1 transparente
        png_1x1 = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c6300010000000500010d0a2db40000000049454e44"
            "ae426082"
        )
        return 200, {"content-type": "image/png", "x-mock": "1"}, png_1x1

    async def fetch_bytes_raw(
        self,
        path: str,
        extra_headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> tuple[int, dict[str, str], bytes]:
        return await self.fetch_bytes(path)

    async def close(self) -> None:
        return None


# ============================================================================
# Helper para integração com VLC (macOS)
# ============================================================================
def open_in_vlc(url: str) -> dict[str, Any]:
    """Tenta abrir uma URL no VLC.app (macOS)."""
    if not url.startswith(("rtsp://", "http://", "https://", "rtmp://")):
        return {"ok": False, "error": f"URL não suportada: {url!r}"}
    try:
        completed = subprocess.run(
            ["open", "-a", "VLC", url],
            check=False,
            capture_output=True,
            timeout=5,
            text=True,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stderr": completed.stderr.strip(),
            "stdout": completed.stdout.strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "error": "'open' não encontrado (não é macOS?)"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout ao chamar 'open'"}
