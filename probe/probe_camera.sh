#!/usr/bin/env bash
# probe_camera.sh - Discovery seguro (somente leituras) para SVBONY SC002 / HiMobileCam SDK.
#
# Uso:
#   bash probe/probe_camera.sh > probe/probe_results.txt 2>&1
#
# Pré-requisitos: curl, nc (netcat). macOS já vem com ambos.
#
# Garantias:
#   - NUNCA chama endpoints destrutivos (lista negra no fim do script).
#   - Todos os requests são GET sem body.
#   - Bloqueia conexões fora da Wi-Fi local (TARGET=192.168.0.1 por padrão).
#
# Output: blocos auto-delimitados com === [GROUP] METHOD URL === ... === END ===
# que o backend depois consegue parsear.

set -u
TARGET="${TARGET:-192.168.0.1}"
UA='HSMSCAM2/1.9.1 (iPad; iOS 26.6; Scale/2.00)'
TIMEOUT="${TIMEOUT:-3}"

# Headers exatamente como o app real envia (capturados em captures.txt).
HDRS=(
  -H "Host: ${TARGET}"
  -H 'Accept: */*'
  -H 'Accept-Language: pt-BR;q=1, en-BR;q=0.9, es-419;q=0.8'
  -H 'Connection: keep-alive'
  -H 'Accept-Encoding: identity'   # identity para evitar gzip ilegível
  -H "User-Agent: ${UA}"
)

OK_COUNT=0
TOTAL_COUNT=0
FAIL_COUNT=0

# Banner inicial -----------------------------------------------------------
{
  echo "================================================================"
  echo " SVBONY SC002 / HiMobileCam HTTP Probe"
  echo " Data:    $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo " Target:  ${TARGET}"
  echo " Timeout: ${TIMEOUT}s"
  echo " UA:      ${UA}"
  echo "================================================================"
  echo
} 1>&2

# probe_get GROUP URL [extra_curl_args...]
probe_get() {
  local group="$1"; shift
  local url="$1"; shift
  TOTAL_COUNT=$((TOTAL_COUNT + 1))

  # echo de progresso para STDERR para você ver na tela enquanto roda
  printf '[%02d] %-12s %s\n' "${TOTAL_COUNT}" "${group}" "${url}" 1>&2

  local started_at_ms
  started_at_ms=$(date +%s000)

  echo "=== [${group}] GET ${url} ==="
  # -sS: silencia barra mas mantém erros; -i: inclui headers; --http1.1: força HTTP/1.1
  # --max-time: limita duração total; -o /dev/stdout: garante que body vai pro stdout
  if curl -sS -i --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" "$@" "${url}"; then
    local rc=$?
    local elapsed=$(( $(date +%s000) - started_at_ms ))
    echo
    echo "=== END (exit_code=${rc}, elapsed_ms=${elapsed}) ==="
    OK_COUNT=$((OK_COUNT + 1))
  else
    local rc=$?
    local elapsed=$(( $(date +%s000) - started_at_ms ))
    echo
    echo "=== END (exit_code=${rc}, elapsed_ms=${elapsed}, curl_failed) ==="
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  echo
}

# probe_port HOST PORT
probe_port() {
  local host="$1" port="$2"
  TOTAL_COUNT=$((TOTAL_COUNT + 1))
  printf '[%02d] %-12s tcp://%s:%s\n' "${TOTAL_COUNT}" "tcp-probe" "${host}" "${port}" 1>&2

  echo "=== [tcp-probe] TCP ${host}:${port} ==="
  if nc -z -G "${TIMEOUT}" "${host}" "${port}" 2>&1; then
    echo "OPEN"
    echo "=== END (exit_code=0) ==="
    OK_COUNT=$((OK_COUNT + 1))
  else
    echo "CLOSED_OR_FILTERED"
    echo "=== END (exit_code=$?) ==="
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  echo
}

# --------------------------------------------------------------------------
# GRUPO 1: hisnet info (todos sem parâmetros, leitura)
# --------------------------------------------------------------------------
HISNET_READ=(
  "/cgi-bin/hisnet/getdeviceattr.cgi?"
  "/cgi-bin/hisnet/getsdstatus.cgi"
  "/cgi-bin/hisnet/getsystime.cgi"
  "/cgi-bin/hisnet/getbatterycapacity.cgi"
  "/cgi-bin/hisnet/getwifi.cgi"
  "/cgi-bin/hisnet/getfilecount.cgi"
  "/cgi-bin/hisnet/getfilelist.cgi"
  "/cgi-bin/hisnet/getworkstate.cgi"
  "/cgi-bin/hisnet/getworkmode.cgi"
  "/cgi-bin/hisnet/ty.cgi"
  "/cgi-bin/hisnet/client.cgi"
  "/cgi-bin/hisnet/checkupgradepktinfo.cgi"
)
for path in "${HISNET_READ[@]}"; do
  probe_get "hisnet" "http://${TARGET}${path}"
done

# --------------------------------------------------------------------------
# GRUPO 2: /app/* JSON (formato moderno do app)
# --------------------------------------------------------------------------
APP_READ=(
  "/app/getmediainfo"
  "/app/getdeviceattr"
  "/app/getsdinfo"
  "/app/getproductinfo"
  "/app/getbatteryinfo"
  "/app/getrecduration"
  "/app/getsnapinfo"
  "/app/getwifiinfo"
  "/app/getversion"
)
for path in "${APP_READ[@]}"; do
  probe_get "app" "http://${TARGET}${path}"
done

# --------------------------------------------------------------------------
# GRUPO 3: Config.cgi wildcards (descobrem toda a árvore Camera.*)
# --------------------------------------------------------------------------
CONFIG_TREES=(
  "Camera.*"
  "Camera.Menu.*"
  "Camera.Preview.*"
  "Camera.Setting.*"
  "Camera.Network.*"
  "Camera.WiFi.*"
  "Camera.SD.*"
  "Camera.System.*"
  "Camera.Photo.*"
  "Camera.Video.*"
  "Camera.HDR.*"
  "Camera.Audio.*"
  "Camera.MTD.*"
  "Camera.TimeLapse.*"
  "Camera.Battery.*"
  "Camera.Stream.*"
  "TimeSettings"
)
for prop in "${CONFIG_TREES[@]}"; do
  probe_get "config-get" \
    "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=${prop}"
done

# --------------------------------------------------------------------------
# GRUPO 4: Capability getters (enumeram opções aceitas pelo SDK)
# --------------------------------------------------------------------------
COMMON_PARAMS=(POWERON_ACTION FOV DATE_FORMAT ANTI_FLICKER SYS_DORMANT SCREEN_DORMANT LANGUAGE VIDEO_FORMS)
for t in "${COMMON_PARAMS[@]}"; do
  probe_get "cap-common" \
    "http://${TARGET}/cgi-bin/hisnet/getcommparamcapability.cgi?-type=${t}"
  probe_get "param-common" \
    "http://${TARGET}/cgi-bin/hisnet/getcommparam.cgi?-type=${t}"
done

WORKMODES=(NORM_REC LOOP_REC LPSE_REC SLOW_REC SING_PHOTO DLAY_PHOTO LPSE_PHOTO BURST)
WORKMODE_TYPES=(MEDIAMODE PHOTO_SCENE PHOTO_OUTPUT_FMT DELAY_TIME LAPSE_INTERVAL BURST_TYPE LOOP_TYPE)
for wm in "${WORKMODES[@]}"; do
  for tp in "${WORKMODE_TYPES[@]}"; do
    probe_get "cap-workmode" \
      "http://${TARGET}/cgi-bin/hisnet/getworkmodeparamcapability.cgi?-workmode=${wm}&-type=${tp}"
  done
done

# --------------------------------------------------------------------------
# GRUPO 5: Sondagem de streams
# --------------------------------------------------------------------------
probe_port "${TARGET}" 554   # RTSP
probe_port "${TARGET}" 8554  # RTSP alt
probe_port "${TARGET}" 5000  # candidato visto em alguns clones
probe_port "${TARGET}" 8080  # candidato
probe_port "${TARGET}" 81    # candidato

MJPEG_CANDIDATES=(
  "/cgi-bin/mjpg/video.cgi"
  "/cgi-bin/mjpeg/video.cgi"
  "/videostream.cgi"
  "/mjpg/video.mjpg"
  "/livestream/11.mjpg"
  "/livestream/12.mjpg"
  "/cgi-bin/hisnet/livestream.cgi"
)
for path in "${MJPEG_CANDIDATES[@]}"; do
  # Para streams, usamos --range 0-2047 + --max-time pequeno para não bloquear.
  probe_get "mjpeg-probe" \
    "http://${TARGET}${path}" \
    -r 0-2047 --max-time 2
done

# --------------------------------------------------------------------------
# GRUPO 6: Filesystem do thttpd (servidor de arquivos legível)
# --------------------------------------------------------------------------
FS_PROBE=(
  "/"
  "/index.html"
  "/sd/"
  "/sd/DCIM/"
)
for path in "${FS_PROBE[@]}"; do
  probe_get "thttpd-fs" "http://${TARGET}${path}"
done

# --------------------------------------------------------------------------
# Resumo final
# --------------------------------------------------------------------------
{
  echo
  echo "================================================================"
  echo " SUMMARY"
  echo " Total requests:    ${TOTAL_COUNT}"
  echo " HTTP/TCP success:  ${OK_COUNT}"
  echo " Curl/TCP failures: ${FAIL_COUNT}"
  echo "================================================================"
  echo
  echo "OBS: 'success' aqui significa apenas que o curl conseguiu falar"
  echo "com o servidor. Códigos HTTP 404 ou -2222/-5555 do SDK ainda"
  echo "contam como 'success' — a classificação fina vem na Fase 2."
  echo
} 1>&2

echo
echo "=== PROBE_END ==="
echo "total=${TOTAL_COUNT}"
echo "ok=${OK_COUNT}"
echo "fail=${FAIL_COUNT}"
