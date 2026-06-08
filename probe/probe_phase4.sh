#!/usr/bin/env bash
# probe_phase4.sh - Fase 4: validar o set FORMATO DO APP (sem Camera.Menu.)
#
# Honeypot capturou:
#   GET /cgi-bin/Config.cgi?action=set&property=SoundRecord&value=OFF
#   GET /cgi-bin/Config.cgi?action=set&property=SoundRecord&value=ON
#
# Sem o prefixo Camera.Menu.! No Fase 3 testei com prefixo e nada persistia.
# Esse probe valida que sem prefixo persiste — e também testa outras keys.
#
# IMPORTANTE: rodando esse probe vai MUDAR SoundRecord 4x (OFF, ON, OFF, ON).
# Pode-se ouvir click/beep. Termina ON (default).
#
# Uso:
#   bash probe/probe_phase4.sh > probe/probe_phase4_results.txt 2>&1

set -u
TARGET="${TARGET:-192.168.0.1}"
UA='HSMSCAM2/1.9.1 (iPad; iOS 26.6; Scale/2.00)'
TIMEOUT="${TIMEOUT:-5}"

HDRS=(
  -H "Host: ${TARGET}"
  -H 'Accept: */*'
  -H 'Accept-Language: pt-BR;q=1, en-BR;q=0.9, es-419;q=0.8'
  -H 'Connection: keep-alive'
  -H 'Accept-Encoding: gzip, deflate'
  -H "User-Agent: ${UA}"
)

TOTAL=0; OK=0
probe_get() {
  local group="$1"; shift
  local url="$1"; shift
  TOTAL=$((TOTAL + 1))
  printf '[%02d] %-10s GET %s\n' "${TOTAL}" "${group}" "${url}" 1>&2
  echo "=== [${group}] GET ${url} ==="
  if curl -sS -i --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" "$@" "${url}"; then
    echo
    echo "=== END (exit_code=0) ==="
    OK=$((OK + 1))
  else
    local rc=$?
    echo
    echo "=== END (exit_code=${rc}, curl_failed) ==="
  fi
  echo
}

# Extrai uma key específica do dump de Camera.Menu.* e mostra
extract_key() {
  local key="$1"
  curl -sS --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" \
    "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.*" 2>/dev/null \
    | grep -E "^Camera\.Menu\.${key}=" || echo "Camera.Menu.${key}=<não encontrado>"
}

{
  echo "================================================================"
  echo " SVBONY SC002 — Probe Fase 4 (validar set formato app oficial)"
  echo " Data:    $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "================================================================"
  echo
  echo "----- Sanity -----"
} 1>&2

echo "=== sanity ==="
curl -sS --max-time 3 "${HDRS[@]}" "http://${TARGET}/app/getbatteryinfo" || { echo "OFFLINE — abortando"; exit 1; }
echo
echo "==="

# ============================================================================
# TESTE 1: SoundRecord (formato exato do app oficial)
# ============================================================================
{
  echo
  echo "----- TESTE 1: SoundRecord (formato app: property=SoundRecord) -----"
} 1>&2

echo "[a] baseline:"
echo "    $(extract_key SoundRecord)"

probe_get "set-app" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=SoundRecord&value=OFF"
sleep 1
echo "[b] depois de set=OFF:"
echo "    $(extract_key SoundRecord)"

probe_get "set-app" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=SoundRecord&value=ON"
sleep 1
echo "[c] depois de set=ON:"
echo "    $(extract_key SoundRecord)"

# ============================================================================
# TESTE 2: HDR (mesma chave que falhou no Fase 3, agora sem prefixo)
# ============================================================================
{
  echo
  echo "----- TESTE 2: HDR (sem prefixo, igual ao app oficial) -----"
} 1>&2

echo "[a] baseline:"
echo "    $(extract_key HDR)"

probe_get "set-app" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=HDR&value=OFF"
sleep 1
echo "[b] depois de set=OFF:"
echo "    $(extract_key HDR)"

probe_get "set-app" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=HDR&value=ON"
sleep 1
echo "[c] depois de set=ON:"
echo "    $(extract_key HDR)"

# ============================================================================
# TESTE 3: Outras keys que valem testar
# ============================================================================
{
  echo
  echo "----- TESTE 3: SoundIndicator, StatusLights (toggle ON->OFF->ON) -----"
} 1>&2

for KEY in SoundIndicator StatusLights; do
  echo
  echo "## ${KEY}"
  echo "[a] baseline: $(extract_key $KEY)"
  probe_get "set-app" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=${KEY}&value=OFF"
  sleep 1
  echo "[b] após OFF: $(extract_key $KEY)"
  probe_get "set-app" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=${KEY}&value=ON"
  sleep 1
  echo "[c] após ON:  $(extract_key $KEY)"
done

# ============================================================================
# TESTE 4: RTSP path do app
# ============================================================================
{
  echo
  echo "----- TESTE 4: confirmar que /liveRTSP/av4:554 está aberto -----"
} 1>&2

# OPTIONS RTSP manual via nc (simulando o ijkplayer)
echo "=== [rtsp-opts] OPTIONS rtsp://${TARGET}:554/liveRTSP/av4 ==="
(printf 'OPTIONS rtsp://%s:554/liveRTSP/av4 RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: probe_phase4\r\n\r\n' "${TARGET}";
 sleep 1) | nc -w 3 "${TARGET}" 554 | head -10
echo
echo "=== END ==="

# Comparar com o path do getmediainfo
echo
echo "=== [rtsp-opts] OPTIONS rtsp://${TARGET}:554/live/tcp/ch1 ==="
(printf 'OPTIONS rtsp://%s:554/live/tcp/ch1 RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: probe_phase4\r\n\r\n' "${TARGET}";
 sleep 1) | nc -w 3 "${TARGET}" 554 | head -10
echo
echo "=== END ==="

# ============================================================================
# Resumo
# ============================================================================
{
  echo
  echo "================================================================"
  echo " SUMMARY (Fase 4)"
  echo " Total requests:    ${TOTAL}"
  echo "================================================================"
} 1>&2

echo
echo "=== PROBE_END ==="
echo "total=${TOTAL}"
echo "ok=${OK}"
