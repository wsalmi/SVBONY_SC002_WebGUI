"""Catálogo de endpoints conhecidos da SVBONY SC002 / HiMobileCam SDK.

Cada `Endpoint` declara:
- group   : aba/categoria onde aparece na UI
- risk    : NORMAL (read), CAREFUL (muda estado) ou DESTRUCTIVE (apaga/reseta)
- status  : confirmed (visto em output.txt), known (documentado no SDK ref),
            experimental (palpite plausível ainda não validado)
- inputs  : descritores tipados para a UI montar o formulário
- builder : função pura que recebe o dict de inputs e devolve (method, path, query, body)

Sem dependências externas. Importável em qualquer lugar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping
from urllib.parse import urlencode


class Risk(str, Enum):
    NORMAL = "NORMAL"
    CAREFUL = "CAREFUL"
    DESTRUCTIVE = "DESTRUCTIVE"


class Status(str, Enum):
    CONFIRMED = "confirmed"      # 200 + corpo válido no probe
    KNOWN = "known"              # documentado no SDK ref, ainda não testado
    EXPERIMENTAL = "experimental"  # palpite plausível
    UNSUPPORTED = "unsupported"  # probe confirmou 404 / não existe


class InputKind(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    CHOICE = "choice"
    DATETIME = "datetime"


@dataclass(frozen=True)
class InputSpec:
    name: str
    kind: InputKind
    label: str
    required: bool = True
    default: str | None = None
    choices: tuple[str, ...] = ()
    placeholder: str = ""
    help: str = ""


@dataclass(frozen=True)
class BuiltRequest:
    method: str
    path: str
    query: tuple[tuple[str, str], ...] = ()

    def url(self, base: str) -> str:
        base = base.rstrip("/")
        if not self.query:
            return f"{base}{self.path}"
        return f"{base}{self.path}?{urlencode(self.query, safe='$.*')}"


@dataclass(frozen=True)
class Endpoint:
    id: str
    label: str
    description: str
    group: str
    risk: Risk
    status: Status
    inputs: tuple[InputSpec, ...] = ()
    builder: Callable[[Mapping[str, Any]], BuiltRequest] = field(repr=False, default=None)  # type: ignore[assignment]
    response_hint: str = ""  # "key_value" | "json" | "html" | "" (auto-detect)

    def build(self, values: Mapping[str, Any]) -> BuiltRequest:
        if self.builder is None:
            raise RuntimeError(f"Endpoint {self.id} has no builder")
        return self.builder(values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "group": self.group,
            "risk": self.risk.value,
            "status": self.status.value,
            "response_hint": self.response_hint,
            "inputs": [
                {
                    "name": i.name,
                    "kind": i.kind.value,
                    "label": i.label,
                    "required": i.required,
                    "default": i.default,
                    "choices": list(i.choices),
                    "placeholder": i.placeholder,
                    "help": i.help,
                }
                for i in self.inputs
            ],
        }


def _simple_get(path: str) -> Callable[[Mapping[str, Any]], BuiltRequest]:
    return lambda _v: BuiltRequest("GET", path)


def _config_get(prop: str) -> Callable[[Mapping[str, Any]], BuiltRequest]:
    return lambda _v: BuiltRequest(
        "GET",
        "/cgi-bin/Config.cgi",
        (("action", "get"), ("property", prop)),
    )


def _config_set(prop: str) -> Callable[[Mapping[str, Any]], BuiltRequest]:
    """Set "longo" com propriedade completa (ex: Camera.Menu.HDR).
    NOTA: o app oficial NÃO usa esta forma — usa `_camera_set` (sem prefixo).
    Mantido só pra casos genéricos (ex: TimeSettings).
    """
    def build(values: Mapping[str, Any]) -> BuiltRequest:
        value = str(values.get("value", ""))
        return BuiltRequest(
            "GET",
            "/cgi-bin/Config.cgi",
            (("action", "set"), ("property", prop), ("value", value)),
        )

    return build


def _camera_set(key: str) -> Callable[[Mapping[str, Any]], BuiltRequest]:
    """Set NO FORMATO DO APP OFICIAL (descoberto via honeypot):
    `property=<key>` SEM o prefixo `Camera.Menu.`. Ex:
        GET /cgi-bin/Config.cgi?action=set&property=SoundRecord&value=ON
    """
    def build(values: Mapping[str, Any]) -> BuiltRequest:
        value = str(values.get("value", ""))
        return BuiltRequest(
            "GET",
            "/cgi-bin/Config.cgi",
            (("action", "set"), ("property", key), ("value", value)),
        )

    return build


# =============================================================================
# Choice catalogs (extraídos do output.txt + SDK refs)
# =============================================================================
VIDEO_RES_CHOICES = ("1080P30", "1080P60", "720P60", "720P30")
HDR_CHOICES = ("ON", "OFF")
ON_OFF = ("ON", "OFF")
LOOP_VIDEO_CHOICES = ("OFF", "1MIN", "3MIN", "5MIN", "10MIN")
PHOTO_BURST_CHOICES = ("OFF", "3_1SEC", "5_1SEC", "10_1SEC")
POWER_OFF_DELAY_CHOICES = ("OFF", "5SEC", "1MIN", "3MIN", "5MIN", "10MIN")
TIMELAPSE_INTERVAL = ("OFF", "1SEC", "3SEC", "5SEC", "10SEC", "30SEC", "1MIN")
TIMELAPSE_DURATION = ("OFF", "30MIN", "1H", "2H", "5H", "12H", "24H")
VIDEO_CLIP_TIME = ("OFF", "1MIN", "3MIN", "5MIN")
TV_SYSTEM = ("PAL", "NTSC")
UPSIDE_DOWN = ("Normal", "Inverted")
VOL_ADJ_CHOICES = ("0", "1", "2", "3", "4", "5")
VOICE_SWITCH = ("LOW", "MID", "HIGH")
UI_MODE = ("VIDEO", "PHOTO", "PLAYBACK")
DEF_MODE = ("VIDEO", "PHOTO")
WORKMODE_CMD = ("START", "STOP")


# =============================================================================
# Definição dos endpoints
# =============================================================================
def _all_endpoints() -> list[Endpoint]:
    items: list[Endpoint] = []

    # ---- Grupo: Status (read-only, baixo risco) -----------------------------
    # Após probe Fase 1: hisnet.* todos 404. Mantidos como UNSUPPORTED só
    # como histórico/documentação (escondidos da UI por default).
    items += [
        Endpoint(
            id="app.getdeviceattr",
            label="Atributos do dispositivo",
            description="UUID, MAC (BSSID), SSID, versões hw/sw, sdkver.",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getdeviceattr"),
            response_hint="json",
        ),
        Endpoint(
            id="app.getbatteryinfo",
            label="Bateria",
            description="Capacidade (%) e estado de carga.",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getbatteryinfo"),
            response_hint="json",
        ),
        Endpoint(
            id="app.getsnapinfo",
            label="Estado de snapshot",
            description="snap_mode, snap_cnt, snap_seq, is_working.",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getsnapinfo"),
            response_hint="json",
        ),
        Endpoint(
            id="app.getsdinfo",
            label="SD card",
            description="Total/free em MB e status do cartão.",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getsdinfo"),
            response_hint="json",
        ),
        Endpoint(
            id="app.getproductinfo",
            label="Produto (manufacturer/model)",
            description="company, model, soc.",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getproductinfo"),
            response_hint="json",
        ),
        Endpoint(
            id="app.getrecduration",
            label="Tempo gravado (atual)",
            description="Duração da gravação corrente em andamento.",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getrecduration"),
            response_hint="json",
        ),
        # Hisnet — todos 404 nesta câmera. Marcados UNSUPPORTED.
        Endpoint(
            id="hisnet.getdeviceattr",
            label="Atributos (hisnet)",
            description="[404 nesta câmera] CGI clássico legado.",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getdeviceattr.cgi?"),
            response_hint="key_value",
        ),
        Endpoint(
            id="hisnet.getsdstatus",
            label="SD status (hisnet)",
            description="[404 nesta câmera]",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getsdstatus.cgi"),
            response_hint="key_value",
        ),
        Endpoint(
            id="hisnet.getbatterycapacity",
            label="Bateria (hisnet)",
            description="[404 nesta câmera]",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getbatterycapacity.cgi"),
            response_hint="key_value",
        ),
        Endpoint(
            id="hisnet.getworkstate",
            label="Estado de operação (hisnet)",
            description="[404 nesta câmera]",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getworkstate.cgi"),
            response_hint="key_value",
        ),
        Endpoint(
            id="hisnet.getworkmode",
            label="Workmode atual (hisnet)",
            description="[404 nesta câmera]",
            group="Status",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getworkmode.cgi"),
            response_hint="key_value",
        ),
    ]

    # ---- Grupo: Câmera (config) ---------------------------------------------
    # CORREÇÃO IMPORTANTE - HONEYPOT CAPTURE (Fase 4):
    # No Fase 3 marquei tudo como UNSUPPORTED porque testei `set
    # property=Camera.Menu.HDR&value=OFF` e nada persistiu. Mas a captura
    # honeypot mostrou o APP OFICIAL fazendo:
    #   GET /cgi-bin/Config.cgi?action=set&property=SoundRecord&value=OFF
    # ou seja, property=<KEY> SEM o prefixo `Camera.Menu.`. Por isso os
    # sets agora usam `_camera_set("X")` que envia property=X.
    # A leitura continua sendo via wildcard `Camera.Menu.*` (que mostra
    # o resultado com o caminho completo). Use o cartão "Menu (todas)"
    # depois do set pra confirmar persistência.
    items += [
        Endpoint(
            id="camera.preview.read",
            label="Preview (todas)",
            description="Lê Camera.Preview.* (MJPEG/RTSP, fps, resolução).",
            group="Camera",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_config_get("Camera.Preview.*"),
            response_hint="key_value",
        ),
        Endpoint(
            id="camera.menu.read",
            label="Menu (todas)",
            description="Lê Camera.Menu.* — todas as opções configuráveis.",
            group="Camera",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_config_get("Camera.Menu.*"),
            response_hint="key_value",
        ),
        Endpoint(
            id="camera.menu.set_video_res",
            label="Resolução de vídeo",
            description="Define Camera.Menu.VideoRes. Verifique relendo o Menu.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Valor", choices=VIDEO_RES_CHOICES, default="1080P30"),
            ),
            builder=_camera_set("VideoRes"),
            response_hint="key_value",
        ),
        Endpoint(
            id="camera.menu.set_hdr",
            label="HDR",
            description="Define Camera.Menu.HDR.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Valor", choices=HDR_CHOICES, default="ON"),
            ),
            builder=_camera_set("HDR"),
            response_hint="key_value",
        ),
        Endpoint(
            id="camera.menu.set_looping",
            label="Loop de vídeo",
            description="Define Camera.Menu.LoopingVideo.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Duração", choices=LOOP_VIDEO_CHOICES, default="5MIN"),
            ),
            builder=_camera_set("LoopingVideo"),
        ),
        Endpoint(
            id="camera.menu.set_videoclip",
            label="Tamanho do clipe",
            description="Define Camera.Menu.VideoClipTime.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Duração", choices=VIDEO_CLIP_TIME, default="1MIN"),
            ),
            builder=_camera_set("VideoClipTime"),
        ),
        Endpoint(
            id="camera.menu.set_photoburst",
            label="Burst de fotos",
            description="Define Camera.Menu.PhotoBurst.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Burst", choices=PHOTO_BURST_CHOICES, default="3_1SEC"),
            ),
            builder=_camera_set("PhotoBurst"),
        ),
        Endpoint(
            id="camera.menu.set_poweroff_delay",
            label="Power-off delay",
            description="Define Camera.Menu.PowerOffDelay.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Atraso", choices=POWER_OFF_DELAY_CHOICES, default="5SEC"),
            ),
            builder=_camera_set("PowerOffDelay"),
        ),
        Endpoint(
            id="camera.menu.set_powersaving",
            label="Power saving",
            description="Define Camera.Menu.PowerSaving (ON/OFF).",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="OFF"),
            ),
            builder=_camera_set("PowerSaving"),
        ),
        Endpoint(
            id="camera.menu.set_lcd",
            label="LCD power",
            description="Liga/desliga LCD (Camera.Menu.LCDPower).",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="ON"),
            ),
            builder=_camera_set("LCDPower"),
        ),
        Endpoint(
            id="camera.menu.set_timelapse",
            label="Time-lapse on/off",
            description="Define Camera.Menu.Timelapse.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="OFF"),
            ),
            builder=_camera_set("Timelapse"),
        ),
        Endpoint(
            id="camera.menu.set_timelapse_interval",
            label="Time-lapse intervalo",
            description="Define Camera.Menu.TimelapseTime.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Duração total", choices=TIMELAPSE_DURATION, default="12H"),
            ),
            builder=_camera_set("TimelapseTime"),
        ),
        Endpoint(
            id="camera.menu.set_videotimelapse",
            label="Time-lapse vídeo",
            description="Define Camera.Menu.VideoTimeLapse.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Duração", choices=TIMELAPSE_DURATION, default="12H"),
            ),
            builder=_camera_set("VideoTimeLapse"),
        ),
        Endpoint(
            id="camera.menu.set_mtd",
            label="Motion detection",
            description="Define Camera.Menu.MTD.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="OFF"),
            ),
            builder=_camera_set("MTD"),
        ),
        Endpoint(
            id="camera.menu.set_upsidedown",
            label="Upside-down",
            description="Inverte imagem (Camera.Menu.UpsideDown).",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=UPSIDE_DOWN, default="Normal"),
            ),
            builder=_camera_set("UpsideDown"),
        ),
        Endpoint(
            id="camera.menu.set_flipsensor",
            label="Flip sensor",
            description="Define Camera.Menu.Flip.Sensor.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="OFF"),
            ),
            builder=_camera_set("Flip.Sensor"),
        ),
        Endpoint(
            id="camera.menu.set_spotmeter",
            label="Spot meter",
            description="Define Camera.Menu.SpotMeter.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="OFF"),
            ),
            builder=_camera_set("SpotMeter"),
        ),
        Endpoint(
            id="camera.menu.set_qshot",
            label="Q-Shot",
            description="Define Camera.Menu.Q-SHOT.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="ON"),
            ),
            builder=_camera_set("Q-SHOT"),
        ),
        Endpoint(
            id="camera.menu.set_statuslights",
            label="LEDs de status",
            description="Define Camera.Menu.StatusLights.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="ON"),
            ),
            builder=_camera_set("StatusLights"),
        ),
        Endpoint(
            id="camera.menu.set_soundindicator",
            label="Beep / som indicador",
            description="Define Camera.Menu.SoundIndicator.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="ON"),
            ),
            builder=_camera_set("SoundIndicator"),
        ),
        Endpoint(
            id="camera.menu.set_soundrecord",
            label="Gravar áudio",
            description="Define Camera.Menu.SoundRecord.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=ON_OFF, default="ON"),
            ),
            builder=_camera_set("SoundRecord"),
        ),
        Endpoint(
            id="camera.menu.set_voiceswitch",
            label="Ganho de microfone",
            description="Define Camera.Menu.VoiceSwitch.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Nível", choices=VOICE_SWITCH, default="MID"),
            ),
            builder=_camera_set("VoiceSwitch"),
        ),
        Endpoint(
            id="camera.menu.set_voladj",
            label="Volume de alto-falante",
            description="Define Camera.Menu.VolAdj (0-5).",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Volume", choices=VOL_ADJ_CHOICES, default="2"),
            ),
            builder=_camera_set("VolAdj"),
        ),
        Endpoint(
            id="camera.menu.set_uimode",
            label="UI Mode",
            description="Define Camera.Menu.UIMode.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Modo", choices=UI_MODE, default="VIDEO"),
            ),
            builder=_camera_set("UIMode"),
        ),
        Endpoint(
            id="camera.menu.set_defmode",
            label="Default mode",
            description="Define Camera.Menu.DefMode.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Modo", choices=DEF_MODE, default="VIDEO"),
            ),
            builder=_camera_set("DefMode"),
        ),
        Endpoint(
            id="camera.menu.set_tvsystem",
            label="TV system",
            description="Define Camera.Menu.TVSystem.",
            group="Camera",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Sistema", choices=TV_SYSTEM, default="PAL"),
            ),
            builder=_camera_set("TVSystem"),
        ),
    ]

    # ---- Grupo: Recording (snapshot + DVR notes) ----------------------------
    # IMPORTANTE: esta câmera é uma DASHCAM. Grava em LOOP automaticamente
    # quando ligada (pastas loop/emr/park). Não existe start/stop de gravação
    # via API — todos esses endpoints retornaram 404 no probe Fase 2.
    items += [
        Endpoint(
            id="app.snapshot",
            label="Tirar foto",
            description="CONFIRMADO: dispara captura imediata. Aparece em event/ no getfilelist.",
            group="Recording",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/snapshot"),
            response_hint="json",
        ),
        Endpoint(
            id="app.getparamvalue",
            label="getparamvalue (inútil)",
            description="[200 OK mas body sempre vazio] Probamos 32 nomes no Fase 3 — todos retornam vazio. Mantido só para reprobing manual.",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            inputs=(InputSpec("name", InputKind.TEXT, "name", placeholder="(nome qualquer)"),),
            builder=lambda v: BuiltRequest(
                "GET",
                "/app/getparamvalue",
                (("name", str(v["name"])),),
            ),
            response_hint="json",
        ),
        # UNSUPPORTED — todos 404 no probe Fase 2
        Endpoint(
            id="app.snap",
            label="snap (não existe)",
            description="[404] Use app.snapshot.",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/app/snap"),
        ),
        Endpoint(
            id="app.startrec",
            label="startrec (não existe)",
            description="[404] Câmera grava em loop automaticamente; sem start/stop via API.",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/app/startrec"),
        ),
        Endpoint(
            id="app.stoprec",
            label="stoprec (não existe)",
            description="[404]",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/app/stoprec"),
        ),
        Endpoint(
            id="app.setparamvalue",
            label="setparamvalue (não existe)",
            description="[404 nesta câmera, apesar de existir em outras action cams do SDK]",
            group="Recording",
            risk=Risk.CAREFUL,
            status=Status.UNSUPPORTED,
            inputs=(
                InputSpec("name", InputKind.TEXT, "name"),
                InputSpec("value", InputKind.TEXT, "value"),
            ),
            builder=lambda v: BuiltRequest(
                "GET",
                "/app/setparamvalue",
                (("name", str(v["name"])), ("value", str(v["value"]))),
            ),
        ),
        Endpoint(
            id="app.startsnap",
            label="startsnap (não existe)",
            description="[404]",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/app/startsnap"),
        ),
        Endpoint(
            id="app.stopsnap",
            label="stopsnap (não existe)",
            description="[404]",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/app/stopsnap"),
        ),
        # hisnet — 404 históricos
        Endpoint(
            id="hisnet.workmode_start",
            label="START workmode (hisnet)",
            description="[404 nesta câmera]",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=lambda _v: BuiltRequest("GET", "/cgi-bin/hisnet/workmodecmd.cgi", (("-cmd", "START"),)),
        ),
        Endpoint(
            id="hisnet.workmode_stop",
            label="STOP workmode (hisnet)",
            description="[404 nesta câmera]",
            group="Recording",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=lambda _v: BuiltRequest("GET", "/cgi-bin/hisnet/workmodecmd.cgi", (("-cmd", "STOP"),)),
        ),
    ]

    # ---- Grupo: Arquivos ----------------------------------------------------
    # A SC002 é uma DASHCAM com EMMC interna (29GB). Estrutura observada:
    #   - loop/   (gravação contínua, EMMC/Normal/F/*.mp4)
    #   - emr/    (eventos de emergência / G-sensor)
    #   - park/   (parking mode)
    #   - event/  (snapshots manuais, EMMC/Photo/F/*.jpg)
    items += [
        Endpoint(
            id="app.getfilelist",
            label="Lista de arquivos",
            description="CONFIRMADO: retorna JSON com 4 pastas (loop/emr/park/event). Aceita ?type=video|photo (mas é ignorado, sempre retorna tudo).",
            group="Files",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getfilelist"),
            response_hint="json",
        ),
        Endpoint(
            id="app.getthumbnail",
            label="getthumbnail (sempre vazio)",
            description="[200 OK mas Content-Length: 0] Mesmo com 'name' válido (verificado Fase 3b). A UI usa o JPEG full como thumbnail no lugar.",
            group="Files",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            inputs=(InputSpec("name", InputKind.TEXT, "name"),),
            builder=lambda v: BuiltRequest(
                "GET",
                "/app/getthumbnail",
                (("name", str(v["name"])),),
            ),
        ),
        Endpoint(
            id="static.file",
            label="Download direto de arquivo",
            description="CONFIRMADO: o lighttpd serve arquivos em http://CAMERA/{name} onde {name} é o campo 'name' do getfilelist. Suporta Range, ETag, Last-Modified.",
            group="Files",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec(
                    "name",
                    InputKind.TEXT,
                    "name",
                    placeholder="ex: EMMC/Photo/F/20260607182633.jpg",
                    help="Path EXATO do getfilelist. Para baixar/streaming use /api/file?name=...",
                ),
            ),
            builder=lambda v: BuiltRequest(
                "GET",
                "/" + str(v["name"]).lstrip("/"),
                (),
            ),
        ),
        Endpoint(
            id="app.deletefile",
            label="Apagar arquivo",
            description="CONFIRMADO: retorna {'result':0,'info':'delete success'} ou {'result':-1,'info':'delete failed'}. Use o 'name' EXATAMENTE como veio do getfilelist (ex: EMMC/Photo/F/...jpg). DESTRUTIVO — não tem undo.",
            group="Files",
            risk=Risk.DESTRUCTIVE,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec(
                    "name",
                    InputKind.TEXT,
                    "name",
                    placeholder="ex: EMMC/Photo/F/20260607182633.jpg",
                    help="Copie o nome diretamente da lista de arquivos.",
                ),
            ),
            builder=lambda v: BuiltRequest(
                "GET",
                "/app/deletefile",
                (("name", str(v["name"])),),
            ),
            response_hint="json",
        ),
        Endpoint(
            id="app.delfile",
            label="delfile (não existe)",
            description="[404] Use app.deletefile (com 'e').",
            group="Files",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            inputs=(InputSpec("name", InputKind.TEXT, "name"),),
            builder=lambda v: BuiltRequest(
                "GET",
                "/app/delfile",
                (("name", str(v["name"])),),
            ),
        ),
        # UNSUPPORTED — confirmados 404 ou inexistentes
        Endpoint(
            id="app.getfileinfo",
            label="getfileinfo (não existe)",
            description="[404]",
            group="Files",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/app/getfileinfo"),
        ),
        Endpoint(
            id="app.listfiles",
            label="listfiles (não existe)",
            description="[404]",
            group="Files",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/app/listfiles"),
        ),
        Endpoint(
            id="hisnet.getfilelist",
            label="getfilelist (hisnet)",
            description="[404 nesta câmera]",
            group="Files",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getfilelist.cgi"),
        ),
        Endpoint(
            id="hisnet.deleteallfiles",
            label="deleteallfiles (hisnet)",
            description="[404 nesta câmera]",
            group="Files",
            risk=Risk.DESTRUCTIVE,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/deleteallfiles.cgi"),
        ),
    ]

    # ---- Grupo: Stream (info/URLs) ------------------------------------------
    items += [
        Endpoint(
            id="app.getmediainfo",
            label="Info de mídia/stream",
            description="JSON com URL RTSP real, porta e transporte (CONFIRMADO: rtsp://192.168.0.1:6035/live/tcp/ch1).",
            group="Stream",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_simple_get("/app/getmediainfo"),
            response_hint="json",
        ),
        Endpoint(
            id="camera.preview.set_mjpeg_status",
            label="MJPEG preview status",
            description="Tenta Camera.Preview.MJPEG.status (Standby/Run). Status 200, efeito incerto.",
            group="Stream",
            risk=Risk.CAREFUL,
            status=Status.EXPERIMENTAL,
            inputs=(
                InputSpec("value", InputKind.CHOICE, "Estado", choices=("Standby", "Run"), default="Run"),
            ),
            builder=_config_set("Camera.Preview.MJPEG.status"),
        ),
    ]

    # ---- Grupo: Sistema -----------------------------------------------------
    items += [
        Endpoint(
            id="camera.set_time",
            label="Sincronizar horário",
            description="Envia agora (separador $) para TimeSettings. CONFIRMADO funcional.",
            group="System",
            risk=Risk.CAREFUL,
            status=Status.CONFIRMED,
            inputs=(
                InputSpec(
                    "datetime",
                    InputKind.DATETIME,
                    "Data/Hora",
                    help="Default = agora (local). Formato interno: YYYY$MM$DD$HH$MM$SS.",
                ),
            ),
            builder=lambda v: BuiltRequest(
                "GET",
                "/cgi-bin/Config.cgi",
                (("action", "set"), ("property", "TimeSettings"), ("value", _format_time(v.get("datetime", "")))),
            ),
        ),
        Endpoint(
            id="camera.get_time",
            label="Ler horário atual",
            description="Lê TimeSettings (formato interno).",
            group="System",
            risk=Risk.NORMAL,
            status=Status.CONFIRMED,
            builder=_config_get("TimeSettings"),
            response_hint="key_value",
        ),
        # hisnet — 404 confirmados
        Endpoint(
            id="hisnet.getsystime",
            label="getsystime (hisnet)",
            description="[404 nesta câmera]",
            group="System",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getsystime.cgi"),
        ),
        Endpoint(
            id="hisnet.getwifi",
            label="getwifi (hisnet)",
            description="[404 nesta câmera]",
            group="System",
            risk=Risk.NORMAL,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/getwifi.cgi"),
        ),
        Endpoint(
            id="hisnet.setwifi",
            label="setwifi (hisnet)",
            description="[404 nesta câmera] - se quiser mudar Wi-Fi, vai precisar de outra rota",
            group="System",
            risk=Risk.DESTRUCTIVE,
            status=Status.UNSUPPORTED,
            inputs=(
                InputSpec("wifissid", InputKind.TEXT, "SSID"),
                InputSpec("wifikey", InputKind.TEXT, "Senha"),
            ),
            builder=lambda v: BuiltRequest(
                "GET",
                "/cgi-bin/hisnet/setwifi.cgi",
                (
                    ("enablewifi", "1"),
                    ("wifissid", str(v["wifissid"])),
                    ("wifikey", str(v["wifikey"])),
                ),
            ),
        ),
        Endpoint(
            id="hisnet.reset",
            label="reset config (hisnet)",
            description="[404 nesta câmera]",
            group="System",
            risk=Risk.DESTRUCTIVE,
            status=Status.UNSUPPORTED,
            builder=_simple_get("/cgi-bin/hisnet/reset.cgi"),
        ),
    ]

    return items


def _format_time(value: str) -> str:
    """Converte 'YYYY-MM-DDTHH:MM:SS' → 'YYYY$MM$DD$HH$MM$SS'.
    Se vier vazio, usa o instante atual local.
    """
    import datetime as _dt
    if not value:
        now = _dt.datetime.now()
    else:
        try:
            now = _dt.datetime.fromisoformat(value)
        except ValueError:
            now = _dt.datetime.now()
    return now.strftime("%Y$%m$%d$%H$%M$%S")


ENDPOINTS: list[Endpoint] = _all_endpoints()
ENDPOINTS_BY_ID: dict[str, Endpoint] = {e.id: e for e in ENDPOINTS}

GROUPS: tuple[str, ...] = (
    "Status",
    "Camera",
    "Recording",
    "Files",
    "Stream",
    "System",
)
