# SVBONY SC002 Console

GUI web local em Python para controlar a SVBONY SC002 (firmware HiMobileCam,
SoC HiSilicon) **sem o app oficial HSMSCAM2**. A interface expõe todas as
funções do app — e várias que o app não libera — e fornece as URLs RTSP/MJPEG
prontas para abrir no VLC externo.

> Identificação: o User-Agent capturado (`HSMSCAM2/1.9.1`) e o firmware
> `SC002_53_2507151656` em [output.txt](output.txt) confirmam o modelo. O
> firmware é um clone do SDK público do HiMobileCam, então a maior parte do
> que está nos refs [TheNitek/ActionCam](https://github.com/TheNitek/ActionCam)
> e [lr-m/Action-Cam-Hacking](https://github.com/lr-m/Action-Cam-Hacking)
> também vale aqui.

## Estrutura

```
Svbony-SC002/
  probe/
    probe_camera.sh             # discovery seguro (só leituras)
    probe_results.example.txt   # fixture sintética para mock mode
    probe_results.txt           # você gera com o script acima
  app/
    main.py                     # FastAPI
    camera_client.py            # httpx async + parser dual + mock + VLC
    endpoints.py                # catálogo tipado de ~50 endpoints
    requirements.txt
    templates/index.html
    static/app.{js,css}
  docs/ENDPOINTS.md             # referência viva
  call_cam.sh                   # script bash original (loop de polling)
  captures.txt                  # tráfego bruto do app
  output.txt                    # respostas curl coletadas
```

## Setup

Requer Python 3.10+ e VLC (opcional, para abrir streams).

```bash
python3 -m venv .venv
.venv/bin/pip install -r app/requirements.txt
```

## Fluxo de uso

### Passo 1 — Probe (uma vez, com a câmera ligada)

```bash
bash probe/probe_camera.sh > probe/probe_results.txt 2>&1
```

O script faz ~70 GETs **só de leitura** contra `192.168.0.1`, mais sondagem
TCP da porta 554 (RTSP) e candidatos MJPEG. Não chama nada destrutivo
(sem `reset`, `delete*`, `setwifi`, `upgrade`, `START/STOP` etc).

Resumo no fim mostra `X/Y endpoints retornaram OK`. Cole esse arquivo no chat
para eu enriquecer o catálogo de endpoints — ou simplesmente use ele direto
em mock mode (`SC002_FIXTURE=probe/probe_results.txt`).

### Passo 2 — Subir a GUI

Modo real (Mac conectado ao Wi-Fi da SC002):

```bash
.venv/bin/uvicorn app.main:app --port 8765
# abre http://127.0.0.1:8765
```

Modo mock (sem câmera, com fixture):

```bash
SC002_MOCK=1 SC002_FIXTURE=probe/probe_results.example.txt \
  .venv/bin/uvicorn app.main:app --port 8765
```

Variáveis de ambiente suportadas:

| var | default | uso |
| --- | --- | --- |
| `SC002_TARGET`  | `192.168.0.1` | IP da câmera |
| `SC002_TIMEOUT` | `3`            | timeout HTTP em segundos |
| `SC002_MOCK`    | (vazio)        | se setado, lê de fixture |
| `SC002_FIXTURE` | `probe/probe_results.txt` | caminho da fixture |

### Passo 3 — Usar a UI

A sidebar tem 7 categorias:

- **Status** — info read-only (bateria, SD, versões, workmode).
- **Camera** — toda árvore `Camera.Menu.*` configurável (HDR, VideoRes,
  PowerSaving, MTD, TimeLapse, etc.). Cada cartão tem um dropdown com os
  valores aceitos pelo firmware e um botão "Executar".
- **Recording** — START/STOP de workmode, troca de workmode, click de tecla.
- **Files** — lista, info e deleção de arquivos no SD.
- **Stream** — RTSP/MJPEG URLs. Botão **Copiar** e **Abrir no VLC**
  (macOS chama `open -a VLC <url>`).
- **System** — sync de horário, leitura/escrita de Wi-Fi, reset (destrutivo).
- **Advanced** — console raw: digite `method/path/query` e dispare qualquer
  request. Útil para opções não expostas nos cartões.

Cada resposta mostra:

- status HTTP colorido (verde 2xx / amarelo 4xx / vermelho erro);
- tabela `KEY=VALUE` parseada (Config.cgi / hisnet) ou JSON formatado (/app/*);
- botão **Copiar curl** com a chamada equivalente, headers incluídos.

Endpoints destrutivos pedem confirmação dupla (digite `EXECUTAR`).

### Passo 4 — Vídeo no VLC

Pela aba **Stream**:

1. Confirme que `rtsp://192.168.0.1:554/livestream/11` apareceu como
   "RTSP descoberto" (vem do JSON do `/app/getmediainfo`). Se não, use os
   candidatos listados.
2. Clique **Abrir no VLC** (macOS) ou **Copiar** e cole em VLC → Media →
   Open Network Stream.
3. Se o stream MJPEG retornar 404, antes vá na aba **Stream** e dispare o
   set "MJPEG preview status = Run" para armar o preview.

## Como o cliente fala com a câmera

- Headers reproduzem byte-a-byte os do app `HSMSCAM2/1.9.1` (vide
  `default_headers()` em [app/camera_client.py](app/camera_client.py)).
- HTTP/1.1, sem TLS, sem autenticação (a câmera assume LAN confiável).
- O quirk `YYYY$MM$DD$HH$MM$SS` em `TimeSettings` é preservado: a URL é
  serializada com `urlencode(safe="$.*")`.
- Parser dual: detecta `KEY=VALUE` (CGI clássico) vs JSON (/app/*) por
  conteúdo, não por content-type — alguns endpoints devolvem JSON com
  `Content-Type: text/plain`.

## Segurança

- A GUI escuta em `127.0.0.1` por padrão; ninguém da rede acessa.
- Endpoints destrutivos (`risk=DESTRUCTIVE`) pedem confirmação manual.
- O console raw permite tudo — use com cuidado.
- A câmera **não** tem autenticação. Quem está na Wi-Fi dela pode tudo.

## Roadmap (não implementado ainda)

- Re-rodar o probe automaticamente e dar diff entre execuções.
- Player MJPEG embutido na UI via `<img>` (atualmente o vídeo é
  delegado ao VLC).
- Exportar o catálogo como coleção Postman / Insomnia.
- Suporte a "perfis" (preset de várias configs aplicadas em batch).

## Referências

- [TheNitek/ActionCam](https://github.com/TheNitek/ActionCam) — catálogo
  `cgi-bin/hisnet/*` + RTSP.
- [lr-m/Action-Cam-Hacking](https://github.com/lr-m/Action-Cam-Hacking) —
  catálogo `/app/*`.
- [docs/ENDPOINTS.md](docs/ENDPOINTS.md) — referência viva deste projeto.
