#!/usr/bin/env bash
# probe_phase2.sh - Discovery dirigido: o que NÃO testamos na fase 1.
#
# Foco:
#   1. /app/* candidatos para ação (start/stop rec, snap, files, params)
#   2. Teste de persistência: SET via Config.cgi seguido de GET para validar
#   3. Variantes alternativas do RTSP descobertas pelo getmediainfo
#
# Uso:
#   bash probe/probe_phase2.sh > probe/probe_phase2_results.txt 2>&1
#
# IMPORTANTE:
#   - Continua SÓ LEITURAS + um único set inócuo (LCDPower=OFF, depois volta).
#   - Não chama deletes / formatação / reset.
#   - Não inicia gravação real — só consulta endpoints que podem revelar
#     o nome da rota; o status retornado já basta para sabermos se existem.

set -u
TARGET="${TARGET:-192.168.0.1}"
UA='HSMSCAM2/1.9.1 (iPad; iOS 26.6; Scale/2.00)'
TIMEOUT="${TIMEOUT:-3}"

HDRS=(
  -H "Host: ${TARGET}"
  -H 'Accept: */*'
  -H 'Accept-Language: pt-BR;q=1, en-BR;q=0.9, es-419;q=0.8'
  -H 'Connection: keep-alive'
  -H 'Accept-Encoding: identity'
  -H "User-Agent: ${UA}"
)

OK_COUNT=0
TOTAL_COUNT=0

{
  echo "================================================================"
  echo " SVBONY SC002 — Probe Fase 2 (dirigida)"
  echo " Data:    $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo " Target:  ${TARGET}"
  echo "================================================================"
} 1>&2

probe_get() {
  local group="$1"; shift
  local url="$1"; shift
  TOTAL_COUNT=$((TOTAL_COUNT + 1))
  printf '[%02d] %-12s %s\n' "${TOTAL_COUNT}" "${group}" "${url}" 1>&2
  local started_at_ms
  started_at_ms=$(date +%s000)
  echo "=== [${group}] GET ${url} ==="
  if curl -sS -i --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" "$@" "${url}"; then
    local elapsed=$(( $(date +%s000) - started_at_ms ))
    echo
    echo "=== END (exit_code=0, elapsed_ms=${elapsed}) ==="
    OK_COUNT=$((OK_COUNT + 1))
  else
    local rc=$?
    local elapsed=$(( $(date +%s000) - started_at_ms ))
    echo
    echo "=== END (exit_code=${rc}, elapsed_ms=${elapsed}, curl_failed) ==="
  fi
  echo
}

# ============================================================================
# 1. Endpoints /app/* de ação (candidatos)
# ============================================================================
APP_ACTION=(
  # Ação direta
  "/app/snap"
  "/app/snapshot"
  "/app/startsnap"
  "/app/stopsnap"
  "/app/startrec"
  "/app/stoprec"
  "/app/recstart"
  "/app/recstop"
  "/app/takephoto"
  "/app/takesnap"
  # Param genérico
  "/app/getparamvalue?name=video_res"
  "/app/getparamvalue?name=language"
  "/app/getparamvalue?name=videores"
  "/app/getparamvalue?name=hdr"
  "/app/getparamvalue?name=loop"
  "/app/getparamvalue?name=poweroff_delay"
  # Listagem
  "/app/getfilelist"
  "/app/getfilelist?path=/sd/DCIM"
  "/app/getfilelist?type=video"
  "/app/getfilelist?type=photo"
  "/app/getfileinfo"
  "/app/listfiles"
  "/app/getthumbnail"
  "/app/getphoto"
  "/app/getvideo"
  # Modo
  "/app/getmode"
  "/app/setmode?mode=video"
  "/app/setmode?mode=photo"
  "/app/getworkmode"
  "/app/getformat"
  # Wi-Fi
  "/app/getwifiinfo"
  "/app/getwifi"
  "/app/getap"
  "/app/getapinfo"
  # Sistema
  "/app/getsysinfo"
  "/app/getstatus"
  "/app/getsysstatus"
  "/app/gettime"
  # Outros possíveis
  "/app/getconfig"
  "/app/getsetting"
  "/app/getall"
  "/app/keepalive"
  "/app/heartbeat"
  "/app/ping"
)
for p in "${APP_ACTION[@]}"; do
  probe_get "app-probe" "http://${TARGET}${p}"
done

# ============================================================================
# 2. Variações do path Camera.Preview.* set (preview MJPEG)
# ============================================================================
CFG_ACTION=(
  "Camera.Preview.MJPEG.status=Run"
  "Camera.Preview.MJPEG.status=Standby"
  "Camera.Menu.IsStreaming=YES"
  "Camera.Menu.IsStreaming=NO"
)
for kv in "${CFG_ACTION[@]}"; do
  key="${kv%=*}"
  val="${kv#*=}"
  probe_get "cfg-set" \
    "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=${key}&value=${val}"
done

# ============================================================================
# 3. TESTE DE PERSISTÊNCIA — set + get pair
# Tentamos virar SoundIndicator OFF e ler de volta para ver se o set "pegou".
# Depois voltamos para ON. Audível, fácil de verificar com ouvido também.
# ============================================================================
{
  echo
  echo "----- TESTE DE PERSISTÊNCIA -----"
  echo "Vamos virar SoundIndicator OFF, ler de volta, virar ON, ler de volta."
  echo "Se o GET refletir o valor que mandamos, o SET persiste."
} 1>&2

probe_get "persist" "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.SoundIndicator"
probe_get "persist" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=Camera.Menu.SoundIndicator&value=OFF"
sleep 1
probe_get "persist" "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.SoundIndicator"
probe_get "persist" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=Camera.Menu.SoundIndicator&value=ON"
sleep 1
probe_get "persist" "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.SoundIndicator"

# ============================================================================
# 4. Mesmo teste via /app/setparamvalue (hipótese: este é o "set real")
# ============================================================================
{
  echo
  echo "----- TESTE de SET VIA /app/setparamvalue -----"
} 1>&2

# Vários nomes possíveis para o mesmo campo
PARAM_NAMES=(SoundIndicator soundindicator sound_indicator sound_ind beep)
for name in "${PARAM_NAMES[@]}"; do
  probe_get "app-param" "http://${TARGET}/app/getparamvalue?name=${name}"
done

# ============================================================================
# 5. TCP probe RTSP em portas alternativas
# ============================================================================
{
  echo
  echo "----- TCP probe RTSP -----"
} 1>&2

for port in 554 6035 7070 8554; do
  TOTAL_COUNT=$((TOTAL_COUNT + 1))
  printf '[%02d] %-12s tcp://%s:%s\n' "${TOTAL_COUNT}" "tcp-probe" "${TARGET}" "${port}" 1>&2
  echo "=== [tcp-probe] TCP ${TARGET}:${port} ==="
  if nc -z -G "${TIMEOUT}" "${TARGET}" "${port}" 2>&1; then
    echo "OPEN"
    echo "=== END (exit_code=0) ==="
    OK_COUNT=$((OK_COUNT + 1))
  else
    echo "CLOSED_OR_FILTERED"
    echo "=== END (exit_code=$?) ==="
  fi
  echo
done

# ============================================================================
# Resumo
# ============================================================================
{
  echo
  echo "================================================================"
  echo " SUMMARY (Fase 2)"
  echo " Total requests:    ${TOTAL_COUNT}"
  echo " HTTP/TCP success:  ${OK_COUNT}"
  echo "================================================================"
} 1>&2

echo
echo "=== PROBE_END ==="
echo "total=${TOTAL_COUNT}"
echo "ok=${OK_COUNT}"
