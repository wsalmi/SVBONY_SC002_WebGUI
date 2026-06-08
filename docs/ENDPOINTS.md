# SVBONY SC002 — Catálogo de endpoints (pós-honeypot)

Documento de referência viva. Atualizado depois da captura honeypot
(`/Volumes/SD/Honeypot/captures.txt`) que pegou o app oficial em ação.

> **TL;DR**: a SC002 tem API completa de **leitura E escrita**. A escrita é
> feita via `Config.cgi action=set` com `property=<KEY>` (SEM o prefixo
> `Camera.Menu.`). Pelo HTTP dá pra:
>
> - Ler estado (bateria, SD, snapshot, produto, RTSP info)
> - **Configurar tudo via Config.cgi** (HDR, VideoRes, SoundRecord, etc.)
> - Tirar foto (`/app/snapshot`)
> - Listar arquivos (`/app/getfilelist`)
> - Baixar arquivo direto (`http://CAMERA/{name}` — suporta Range)
> - Streaming HTML5 de vídeo (Range requests OK)
> - Apagar arquivo (`/app/deletefile`)
> - Obter URL do stream RTSP

## ★ Stream RTSP correto (do app oficial)

```
rtsp://192.168.0.1:554/liveRTSP/av4
```

Capturado do app oficial (`User-Agent: ijkplayer`). O `/app/getmediainfo`
retorna `/live/tcp/ch1` na porta 6035, mas isso parece ser ignorado pelo app
— o **path real** é `/liveRTSP/av4` na porta 554.

O app envia `OPTIONS rtsp://...:554/liveRTSP/av4` a cada ~1Hz como
keepalive enquanto a tela de preview está aberta.

## ★ Sets via Config.cgi — formato correto

Capturado do app oficial:

```
GET /cgi-bin/Config.cgi?action=set&property=SoundRecord&value=OFF
GET /cgi-bin/Config.cgi?action=set&property=SoundRecord&value=ON
GET /cgi-bin/Config.cgi?action=set&property=TimeSettings&value=2026$06$08$11$49$07
```

**A propriedade NÃO leva o prefixo `Camera.Menu.`**. Apenas o nome final da
key. O Fase 3 testou com prefixo (`property=Camera.Menu.HDR`) e nada
persistia — daí o erro de classificá-los como UNSUPPORTED. Agora estão
todos CONFIRMED de novo.

A leitura continua sendo via wildcard: `Config.cgi?action=get&property=Camera.Menu.*`
(retorna todas as keys com o prefixo completo).

Status:
- `confirmed`   — 200 + corpo válido no probe
- `experimental`— ainda não testado nesta câmera; palpite do SDK
- `unsupported` — probe confirmou 404 → endpoint **não existe** aqui

## Identificação real (de `/app/getdeviceattr`)

```json
{
  "uuid":   "80:9d:65:e4:23:32",
  "softver":"SC002_53_2507151656",
  "hwver":  "SC002_53_2507151656",
  "ssid":   "SC002_2332",
  "bssid":  "80:9d:65:e4:23:32",
  "camnum": 1,
  "sdkver": "1.0"
}
```

Produto (de `/app/getproductinfo`):

```json
{"model":"DVR","company":"SGK","soc":"SOC"}
```

> `company=SGK` (Shenzhen General Kingway, OEM Chinês) + `model=DVR` confirma
> que o firmware é a engine genérica que muitas marcas embutem; a SVBONY só
> rebrandou.

## Stream RTSP — A descoberta principal

`/app/getmediainfo` retornou:

```json
{
  "rtsp":      "rtsp://192.168.0.1/live/tcp/ch1",
  "transport": "tcp",
  "port":      "6035"
}
```

Implicações:

- O path é `/live/tcp/ch1` (NÃO `/livestream/11` como em outras cams do SDK).
- A porta canônica é **6035**, não 554. As duas portas estão abertas (probe TCP
  confirmou) — provavelmente a 554 só faz redirect/handshake.
- Transport TCP-only nesta versão.
- Único canal (`ch1`); sub-stream (ch2) provavelmente não existe.

URLs para tentar no VLC:

```
rtsp://192.168.0.1/live/tcp/ch1            ← o que getmediainfo devolve
rtsp://192.168.0.1:6035/live/tcp/ch1       ← porta declarada no JSON
rtsp://192.168.0.1:554/live/tcp/ch1        ← porta padrão RTSP (também abre)
```

A GUI agora gera as três automaticamente a partir do JSON.

## API surface real

Esta câmera fala APENAS **2 dialetos** (de 3 originalmente assumidos):

| Família | Confirmado | Observação |
| --- | --- | --- |
| `/app/*` (JSON) | 7 endpoints | format `{"result":0,"info":{...}}` |
| `/cgi-bin/Config.cgi?action=(get\|set)&property=Camera.Menu.*` ou `Camera.Preview.*` | sim | só estas duas subárvores têm conteúdo |
| `/cgi-bin/Config.cgi` outras subárvores (`Setting.*`, `Network.*`, `WiFi.*`, `SD.*`, `System.*`, `Photo.*`, `Video.*`, `HDR.*`, `Audio.*`, `MTD.*`, `TimeLapse.*`, `Battery.*`, `Stream.*`) | 200 mas **body vazio** | propriedades não existem |
| `/cgi-bin/hisnet/*.cgi` | **404 em todos** | não implementado neste firmware |
| HTTP MJPEG (várias variantes) | **404 em todos** | preview MJPEG não é exposto via HTTP |

## Endpoints CONFIRMED (200 + corpo)

### `/app/*` — JSON (todos GET)

| Endpoint | Função | Exemplo de resposta |
| --- | --- | --- |
| `/app/getdeviceattr` | Identificação | `{"uuid":"80:9d:65:e4:23:32","softver":"SC002_53_2507151656",...}` |
| `/app/getbatteryinfo` | Bateria | `{"capacity":4,"charge":1}` |
| `/app/getsnapinfo` | Estado snapshot | `{"is_working":0,"snap_mode":3,"snap_cnt":200,"snap_seq":0}` |
| `/app/getsdinfo` | Storage (EMMC interna, em MB) | `{"status":0,"free":27561,"total":29816}` |
| `/app/getproductinfo` | Produto | `{"model":"DVR","company":"SGK","soc":"SOC"}` |
| `/app/getrecduration` | Tempo gravado atual | `{"duration":0}` |
| `/app/getmediainfo` | URL/porta RTSP | `{"rtsp":"rtsp://192.168.0.1/live/tcp/ch1","transport":"tcp","port":"6035"}` |
| **`/app/snapshot`** ★ | **Tira foto** | `{"result":0,"info":"set success"}` (arquivo aparece em `event/`) |
| **`/app/getfilelist`** ★ | **Lista todos os arquivos** | JSON com 4 folders (`loop` / `emr` / `park` / `event`) — ver abaixo |
| `/app/getthumbnail?name=X` | Thumbnail | 200 OK (precisa de `name=` válido vindo do getfilelist) |
| `/app/getparamvalue?name=X` | Sondagem genérica | 200 OK mas body vazio para todos os nomes testados; o nome correto é desconhecido |

★ Descobertos no probe Fase 2.

### Resposta do `getfilelist`

```json
{"result":0,"info":[
  {"folder":"loop", "files":[{"name":"EMMC/Normal/F/20270101001856.mp4","duration":125,"size":127857,"createtime":1798733936,"type":2}, ...], "count":0},
  {"folder":"emr",   "files":[], "count":0},
  {"folder":"park",  "files":[], "count":0},
  {"folder":"event", "files":[{"name":"EMMC/Photo/F/20260607182633.jpg","duration":0,"size":2090,"createtime":1780827993,"type":1}, ...], "count":0}
]}
```

- `type`: `1` = foto, `2` = vídeo
- `duration`: segundos
- `size`: bytes
- `createtime`: epoch (unix ts)
- Estrutura de pastas é típica de **dashcam**:
  - `loop` — gravação contínua (segmentada de 1min ou 5min de acordo com `Camera.Menu.VideoClipTime` / `Camera.Menu.LoopingVideo`)
  - `emr` — eventos de emergência (G-sensor)
  - `park` — parking mode
  - `event` — snapshots manuais via `/app/snapshot`
- `?path=...` e `?type=...` são **aceitos mas ignorados** — retornam sempre tudo.

### `Config.cgi` — KEY=VALUE

| Endpoint | Função |
| --- | --- |
| `GET /cgi-bin/Config.cgi?action=get&property=Camera.Menu.*` | Lê toda a árvore Camera.Menu (35 pares conhecidos) |
| `GET /cgi-bin/Config.cgi?action=get&property=Camera.Preview.*` | Lê preview MJPEG/RTSP info |
| `GET /cgi-bin/Config.cgi?action=set&property=TimeSettings&value=YYYY$MM$DD$HH$MM$SS` | Sincroniza RTC. **Único SET que de fato funciona** |
| `GET /cgi-bin/Config.cgi?action=set&property=Camera.Menu.<X>&value=<Y>` | Retorna 200 mas **NÃO PERSISTE** (confirmado Fase 3) |

### Camera.Menu.* — propriedades observadas

```
Camera.Menu.FWversion        = SC002_53_2507151656
Camera.Menu.DefMode          = VIDEO
Camera.Menu.UIMode           = VIDEO
Camera.Menu.VideoRes         = 1080P30
Camera.Menu.HDR              = ON
Camera.Menu.IsStreaming      = NO
Camera.Menu.LCDPower         = OFF
Camera.Menu.LoopingVideo     = 5MIN
Camera.Menu.MTD              = OFF
Camera.Menu.PhotoBurst       = 3_1SEC
Camera.Menu.PowerOffDelay    = 5SEC
Camera.Menu.PowerSaving      = OFF
Camera.Menu.Q-SHOT           = ON
Camera.Menu.SoundIndicator   = ON
Camera.Menu.SoundRecord      = ON
Camera.Menu.SpotMeter        = OFF
Camera.Menu.StatusLights     = ON
Camera.Menu.TV               = NONE
Camera.Menu.TVSystem         = PAL
Camera.Menu.UpsideDown       = Normal
Camera.Menu.VideoClipTime    = 1MIN
Camera.Menu.VoiceSwitch      = MID
Camera.Menu.VolAdj           = 2
Camera.Menu.Flip.Sensor      = OFF
Camera.Menu.TimeLapseRecord  = OFF
Camera.Menu.Timelapse        = OFF
Camera.Menu.TimelapseTime    = 12H
Camera.Menu.VideoTimeLapse   = 12H
Camera.Menu.MemoryType       = SDCARD
Camera.Menu.SD0              = READY
Camera.Menu.CardInfo.*       = (4 sub-campos: vida útil etc)
```

### Camera.Preview.* — propriedades observadas

```
Camera.Preview.MJPEG.bitrate         = 2000000
Camera.Preview.MJPEG.fps             = 30
Camera.Preview.MJPEG.w               = 720
Camera.Preview.MJPEG.h               = 1280
Camera.Preview.MJPEG.status          = Standby
Camera.Preview.MJPEG.status.mode     = Videomode
Camera.Preview.MJPEG.status.record   = Standby
Camera.Preview.MJPEG.status.MovieAudio = ON
Camera.Preview.MJPEG.WarningMSG      = ACTIVE
Camera.Preview.MJPEG.TimeStamp.*     = (year/month/day/hour/minute/second)
Camera.Preview.RTSP.av               = 4
```

## Endpoints UNSUPPORTED (404 confirmado)

Toda a família `/cgi-bin/hisnet/*.cgi` retorna 404 nesta câmera. A engine
HiMobileCam que o SDK refs documentam tem uma camada CGI que SGK **removeu**
ou nunca incluiu. Todas as ações precisam ser feitas via `/app/*` ou
`Config.cgi`.

Lista de 404s confirmados:
`getdeviceattr.cgi`, `getsdstatus.cgi`, `getsystime.cgi`, `getbatterycapacity.cgi`,
`getwifi.cgi`, `getfilecount.cgi`, `getfilelist.cgi`, `getworkstate.cgi`,
`getworkmode.cgi`, `ty.cgi`, `client.cgi`, `checkupgradepktinfo.cgi`,
`getcommparamcapability.cgi`, `getcommparam.cgi`,
`getworkmodeparamcapability.cgi` (todas combinações de workmode × type).

Também 404: todos os caminhos MJPEG (`/cgi-bin/mjpg/*`, `/livestream/*.mjpg`,
`/videostream.cgi`, `/mjpg/video.mjpg`) e o filesystem do thttpd (`/`,
`/index.html`, `/sd/`, `/sd/DCIM/`).

## Conclusões — versão corrigida pós-honeypot

### A SC002 TEM API de escrita (corrigindo o Fase 3)

O Fase 3 testou `set property=Camera.Menu.HDR&value=OFF` e nada persistia.
A captura honeypot revelou que o formato real é **sem o prefixo**:

```
GET /cgi-bin/Config.cgi?action=set&property=HDR&value=OFF
```

Por isso os 24 sets agora estão de volta como **CONFIRMED** com builder
`_camera_set("HDR")` que envia o formato certo.

O Fase 4 (`probe/probe_phase4.sh`) faz a validação fechada: lê
`Camera.Menu.SoundRecord`, faz `set property=SoundRecord&value=OFF`, relê e
verifica que mudou. Se passou → toda a tabela de sets está correta.

### O que o app oficial NÃO faz

A captura mostra que o app oficial:
- Polla `Camera.Menu.*`, `Camera.Preview.*`, `app/getbatteryinfo` em loop
- Sincroniza RTC 2x na inicialização
- Faz set quando o usuário toca em algo (vimos `SoundRecord=OFF/ON`)
- Mantém RTSP keepalive (`OPTIONS rtsp://...:554/liveRTSP/av4`)

**NÃO usa nesta sessão capturada**:
- `/app/snapshot`, `/app/getfilelist`, `/app/deletefile` — provavelmente
  porque o usuário só ficou na tela de preview, sem ir na galeria.
- `/app/getthumbnail` — nem na galeria (provavelmente o app usa o JPEG
  full como thumbnail, igual à nossa GUI).
- `/app/setparamvalue` — não existe nesta câmera mesmo.
- Nenhum endpoint `/cgi-bin/hisnet/*` — esses são de outra família de SDK.

### Endpoints CONFIRMED de ação

| Endpoint | Função |
| --- | --- |
| `GET /app/snapshot` | Tira foto, grava em `event/` |
| `GET /app/deletefile?name=...` | Apaga arquivo. Retorna `{"result":0,"info":"delete success"}` ou `{"result":-1,"info":"delete failed"}` |
| `GET /app/getthumbnail?name=...` | Retorna JPEG binário do thumbnail (usa `name` do `getfilelist`) |
| `GET /cgi-bin/Config.cgi?action=set&property=TimeSettings&value=...` | Sincroniza RTC |

### Endpoints UNSUPPORTED — confirmados

Fase 3 adicionou aos 404s já conhecidos:
- `/app/delfile` (mas `/app/deletefile` com 'e' **existe** ★)
- `/app/delete`, `/app/rmfile`, `/app/removefile`, `/app/unlink`, `/cgi-bin/delete.cgi`
- `/app/getfile`, `/app/getphoto`, `/app/getvideo`, `/app/getmedia`, `/cgi-bin/get_file`, `/cgi-bin/getfile.cgi`
- `/app/getparamvalue?name=X` — endpoint existe (200) mas body sempre vazio
  para todos os 32 nomes testados; é inútil sem documentação do nome correto.

## Conclusões do Fase 3b — Download resolvido

**Path canônico de download:** o lighttpd serve **direto** o arquivo em
`http://CAMERA/{name}` onde `{name}` é EXATAMENTE o campo `name` devolvido
pelo `/app/getfilelist` (ex: `EMMC/Photo/F/20260607182633.jpg`).

Headers de resposta (HEAD request):

```
HTTP/1.1 200 OK
Content-Type: image/jpeg              # já vem correto para JPEG/MP4
Accept-Ranges: bytes                  # suporta seek!
ETag: "-1236318658"                   # cacheável
Last-Modified: Mon, 25 May 2026 ...
Content-Length: 2033836
```

Com `Range: bytes=0-31`:

```
HTTP/1.1 206 Partial Content
Content-Range: bytes 0-31/2033836
����..JFIF..........              # FFD8FF + JFIF = JPEG válido
```

**Implicações para a GUI:**

1. `<img src="http://camera/EMMC/Photo/...jpg">` funciona direto, sem proxy
   (mas usamos `/api/thumbnail` proxy para evitar mixed-content e CORS).
2. `<video src="...">` HTML5 funciona com seek nativo, porque
   `Accept-Ranges: bytes` está habilitado.
3. Cache do browser funciona (ETag).

**Variantes que NÃO funcionam** (todos 404):
- `/EMMC/{name}` com `EMMC/` duplicado
- `/sd/{name}`, `/mnt/{name}`, `/mmc/{name}`, `/data/{name}`, `/storage/{name}`
- `/cgi/{name}`, `/files/{name}`, `/dav/{name}`
- `/app/file?name=`, `/app/download?name=`, `/app/getfile?name=`
- `/app/get?name=`, `/app/getmedia?name=`, `/app/media?name=`
- `/app/loadfile?name=`, `/app/readfile?name=`
- `/Photo/F/...` sem prefixo `EMMC/`

**`/app/getthumbnail`** retorna `200 OK Content-Length: 0` mesmo com `name`
válido vindo do `getfilelist`. É inútil. A GUI usa o JPEG full como
thumbnail (são pequenos, 2-3 MB cada).
