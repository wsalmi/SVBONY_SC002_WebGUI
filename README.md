# SVBONY SC002 Console

GUI web local, em Python, para operar a dashcam SVBONY SC002 sem o aplicativo oficial HSMSCAM2. O computador entra no Wi-Fi da câmera e esta interface consulta o firmware HiMobileCam por HTTP: lê o estado, grava opções de menu, tira foto, lista e baixa arquivos do armazenamento interno e mostra a URL RTSP para abrir no VLC.

O firmware visto em [output.txt](output.txt) é `SC002_53_2507151656`. O tráfego do app oficial usa o User-Agent `HSMSCAM2/1.9.1`. Em `/app/getproductinfo` a unidade se apresenta como DVR da família SGK, um clone desse SDK. Parte do que [TheNitek/ActionCam](https://github.com/TheNitek/ActionCam) e [lr-m/Action-Cam-Hacking](https://github.com/lr-m/Action-Cam-Hacking) descrevem vale aqui. Nesta câmera a família `/cgi-bin/hisnet/*.cgi` responde 404. O catálogo medido está em [docs/ENDPOINTS.md](docs/ENDPOINTS.md).

## Funcionalidades

A barra lateral lista os seis grupos do catálogo e um console **Advanced**. Itens com status `unsupported` ficam ocultos até marcar "mostrar unsupported".

- **Status** — identificação, bateria, armazenamento, produto, estado do snapshot e duração da gravação (`/app/getdeviceattr`, `/app/getbatteryinfo`, `/app/getsdinfo`, `/app/getproductinfo`, `/app/getsnapinfo`, `/app/getrecduration`).
- **Camera** — leitura de `Camera.Menu.*` e `Camera.Preview.*`, e ajustes com `Config.cgi?action=set&property=<chave>&value=<valor>`. A chave vai sem o prefixo `Camera.Menu.` (formato visto no app oficial). Há cartões para resolução, HDR, loop, duração do clipe, burst, energia, LCD, time-lapse, detecção de movimento, orientação, áudio, LEDs e modos de interface.
- **Recording** — foto imediata com `/app/snapshot`, gravada na pasta `event`. O vídeo da dashcam segue em loop (`loop`, `emr`, `park`) enquanto a câmera está ligada. Os candidatos de start/stop estão no catálogo como `unsupported`.
- **Files** — `/app/getfilelist` devolve as pastas `loop`, `emr`, `park` e `event`. A lista mostra prévia, player HTML5, download e exclusão. O lighttpd da câmera serve o arquivo em `http://<câmera>/<name>`, com `Accept-Ranges: bytes`. A GUI proxia isso em `/api/file` e `/api/thumbnail`.
- **Stream** — a primeira URL é a capturada do app oficial: `rtsp://<ip>:554/liveRTSP/av4`. Se `/app/getmediainfo` responder, a UI também lista o path que esse JSON declara (`/live/tcp/ch1`, porta 6035 no probe). Cada URL tem **Copiar** e **Abrir no VLC**.
- **System** — leitura e ajuste do relógio (`TimeSettings`, valor `YYYY$MM$DD$HH$MM$SS`).
- **Advanced** — método, path e query enviados à câmera sem validação.

Cada resposta mostra o status HTTP, o corpo em tabela `KEY=VALUE` ou JSON, e o botão **Copiar curl**. O indicador no topo consulta `/api/health` a cada 10 segundos.

## Stack

- Python, [FastAPI](https://fastapi.tiangolo.com/) e Uvicorn
- Cliente HTTP assíncrono com [httpx](https://www.python-httpx.org/)
- Templates [Jinja2](https://jinja.palletsprojects.com/) em `app/templates/index.html`
- Front-end estático, sem build (`app/static/app.js` e `app/static/app.css`)
- Sondas em bash (`curl` e `nc`)

[app/requirements.txt](app/requirements.txt) pede FastAPI, Uvicorn, httpx e Jinja2. Na instalação verificada o pip resolveu FastAPI 0.162.0 e Uvicorn 0.54.0, ambos com `Requires-Python: >=3.10`.

## Requisitos

- Python 3.10 ou superior. Os comandos abaixo foram executados com Python 3.12.3.
- Rede da câmera para o modo real. O IP padrão é `192.168.0.1`.
- `bash`, `curl` e `nc` para os scripts em `probe/`. `probe_camera.sh` chama `nc -z -G` (timeout do netcat do macOS). O cabeçalho do script indica que o macOS já traz `curl` e `nc`.
- VLC, se quiser ver o stream. **Abrir no VLC** executa `open -a VLC` e funciona no macOS. Nos outros sistemas, copie a URL e abra em Media → Open Network Stream.

## Instalação

Na raiz do repositório:

```bash
python3 -m venv .venv
.venv/bin/pip install -r app/requirements.txt
```

## Como executar

Modo real, com o computador no Wi-Fi da SC002:

```bash
.venv/bin/uvicorn app.main:app --port 8765
```

Abra http://127.0.0.1:8765. Sem `--host`, o Uvicorn escuta em `127.0.0.1`. O docstring de `app/main.py` também cita a flag `--reload` do Uvicorn.

Modo mock, sem câmera, com a fixture sintética:

```bash
SC002_MOCK=1 SC002_FIXTURE=probe/probe_results.example.txt \
  .venv/bin/uvicorn app.main:app --port 8765
```

Esse comando foi executado neste repositório. `GET /` respondeu 200 e `GET /api/health` devolveu `{"online": true, "mock": true}`.

`call_cam.sh` é o laço bash anterior à GUI. Ele consulta em ciclo alguns endpoints de status e só para com interrupção manual. `TARGET` define o IP (padrão `192.168.0.1`).

### Sondas

`probe/probe_camera.sh` emite 121 GETs de leitura e 5 sondagens TCP (portas 554, 8554, 5000, 8080 e 81). O script não chama reset, delete, setwifi, upgrade nem START/STOP.

```bash
bash probe/probe_camera.sh > probe/probe_results.txt 2>&1
```

`TARGET` (padrão `192.168.0.1`) e `TIMEOUT` (padrão `3` segundos neste script) valem para as sondas. As fases seguintes mudam estado na câmera:

| Script | O que faz na câmera |
| --- | --- |
| `probe/probe_phase2.sh` | GETs de candidatos `/app/*` (inclui `/app/snapshot`), sets de `Camera.Preview.MJPEG.status` e `Camera.Menu.IsStreaming`, e um ciclo de `Camera.Menu.SoundIndicator` em OFF e de volta a ON. Também sonda as portas TCP 554, 6035, 7070 e 8554. |
| `probe/probe_phase3.sh` | Chama `/app/snapshot` uma vez e testa apagar com um nome inválido. |
| `probe/probe_phase3b.sh` | HEAD e GET de caminhos de download. |
| `probe/probe_phase4.sh` | Grava `SoundRecord`, `HDR`, `SoundIndicator` e `StatusLights` em OFF e depois em ON, e envia `OPTIONS` RTSP para `/liveRTSP/av4`. Essas chaves terminam em ON. |

O uso de cada um está no comentário do próprio script, no formato `bash probe/<script>.sh > probe/<script>_results.txt 2>&1`. Já há saídas em `probe/probe_results.txt`, `probe/probe_phase2_results.txt`, `probe/probe_phase3_results.txt` e `probe/probe_phase3b_results.txt`.

O repositório não inclui suíte de testes automatizados.

## Variáveis de ambiente

Nenhuma delas é segredo. A câmera não autentica o HTTP.

| Variável | Padrão | Onde |
| --- | --- | --- |
| `SC002_TARGET` | `192.168.0.1` | IP usado pela GUI |
| `SC002_TIMEOUT` | `3` | timeout HTTP da GUI, em segundos |
| `SC002_MOCK` | vazio | qualquer valor não vazio lê a fixture em vez da câmera |
| `SC002_FIXTURE` | `probe/probe_results.txt` | caminho da fixture no modo mock |
| `TARGET` | `192.168.0.1` | IP usado por `probe/*.sh` e `call_cam.sh` |
| `TIMEOUT` | `3` ou `5` | timeout dos scripts de sonda, em segundos |

## API local da GUI

| Método | Caminho | Função |
| --- | --- | --- |
| `GET` | `/` | página da interface |
| `GET` | `/api/health` | consulta `/app/getbatteryinfo` |
| `GET` | `/api/info` | alvo, modo mock, grupos e total de endpoints |
| `GET` | `/api/endpoints` | catálogo que a UI renderiza |
| `POST` | `/api/call/{endpoint_id}` | dispara um item do catálogo |
| `POST` | `/api/raw` | request livre (`method`, `path` e `query`, ou `url`) |
| `GET` | `/api/stream-urls` | URLs RTSP sugeridas |
| `POST` | `/api/open-in-vlc` | abre uma URL no VLC no macOS |
| `GET` | `/api/file?name=` | proxy do arquivo, repassando `Range` |
| `GET` | `/api/thumbnail?name=` | JPEG da foto; `.mp4` recebe um placeholder |

`app/endpoints.py` declara 64 endpoints: 39 `confirmed`, 1 `experimental` (status do preview MJPEG) e 24 `unsupported`.

## Protocolo com a câmera

- HTTP/1.1, sem TLS e sem autenticação. Quem está no Wi-Fi da câmera controla o aparelho.
- Os headers saem de `default_headers()` em [app/camera_client.py](app/camera_client.py). O User-Agent é `HSMSCAM2/1.9.1 (iPad; iOS 26.6; Scale/2.00)`. `Accept-Encoding` vai como `identity` para o corpo chegar legível. Na captura original do app o valor era `gzip, deflate`.
- A query preserva `$`, `.` e `*` (`urlencode` com `safe="$.*"`), o que mantém `TimeSettings` (`YYYY$MM$DD$HH$MM$SS`) e curingas como `Camera.Menu.*`.
- O parser escolhe JSON ou `KEY=VALUE` pelo conteúdo. Vários `/app/*` devolvem JSON com `Content-Type: text/plain`.
- A escrita de menu confirmada no tráfego do app é `GET /cgi-bin/Config.cgi?action=set&property=SoundRecord&value=ON`, com o nome curto da propriedade.
- O stream usado pelo app oficial (`ijkplayer`) é `rtsp://<ip>:554/liveRTSP/av4`. Os caminhos HTTP de MJPEG sondados em `probe/probe_camera.sh` responderam 404.
- O download usa o campo `name` de `/app/getfilelist` como path, por exemplo um caminho sob `EMMC/`.

## Estrutura

```
app/
  main.py                  # FastAPI: página e rotas /api/*
  camera_client.py         # httpx, parser, mock e abertura no VLC
  endpoints.py             # catálogo tipado (64 endpoints)
  requirements.txt
  templates/index.html
  static/app.js
  static/app.css
probe/
  probe_camera.sh          # sonda somente leitura
  probe_phase2.sh
  probe_phase3.sh
  probe_phase3b.sh
  probe_phase4.sh
  probe_results.example.txt
  probe_results.txt
  probe_phase2_results.txt
  probe_phase3_results.txt
  probe_phase3b_results.txt
docs/ENDPOINTS.md          # referência dos endpoints da câmera
call_cam.sh                # polling bash original
captures.txt               # tráfego bruto do app oficial
output.txt                 # respostas curl coletadas
```

## Segurança

- Com o comando de execução acima, a GUI escuta só em `127.0.0.1`.
- Um endpoint com `risk=DESTRUCTIVE` pede a palavra `EXECUTAR` antes do envio. Na galeria, **apagar** pede confirmação do navegador e chama `/app/deletefile`.
- O console **Advanced** encaminha o método, o path e a query que você digitar.
- A câmera aceita qualquer cliente na rede Wi-Fi dela.

## Licença

Este repositório não inclui arquivo de licença.

## Referências

- [docs/ENDPOINTS.md](docs/ENDPOINTS.md) — catálogo medido nesta SC002
- [TheNitek/ActionCam](https://github.com/TheNitek/ActionCam) — família `cgi-bin/hisnet/*` e RTSP em outras câmeras do mesmo SDK
- [lr-m/Action-Cam-Hacking](https://github.com/lr-m/Action-Cam-Hacking) — família `/app/*`
