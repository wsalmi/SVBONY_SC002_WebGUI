#!/usr/bin/env bash
# probe_phase3.sh - Fase 3: download de arquivo + persistência via wildcard.
#
# Foco:
#   1. Como BAIXAR um arquivo listado pelo /app/getfilelist (path = EMMC/Photo/F/...)
#   2. Como obter o thumbnail (já sabemos que /app/getthumbnail existe)
#   3. Como deletar (palpite /app/delfile, /app/deletefile)
#   4. Teste de persistência via Camera.Menu.* wildcard (não propriedade isolada)
#   5. Descobrir nomes válidos de /app/getparamvalue (varrendo nomes
#      observados em Camera.Menu.*)
#
# Uso:
#   bash probe/probe_phase3.sh > probe/probe_phase3_results.txt 2>&1
#
# AVISO: chama /app/snapshot 1x para gerar um arquivo "fresco" para teste.
#        NÃO apaga nada (delfile só é testado com nome inválido para evitar
#        risco de deletar real).

set -u
TARGET="${TARGET:-192.168.0.1}"
UA='HSMSCAM2/1.9.1 (iPad; iOS 26.6; Scale/2.00)'
TIMEOUT="${TIMEOUT:-5}"

HDRS=(
  -H "Host: ${TARGET}"
  -H 'Accept: */*'
  -H 'Accept-Language: pt-BR;q=1, en-BR;q=0.9, es-419;q=0.8'
  -H 'Connection: keep-alive'
  -H 'Accept-Encoding: identity'
  -H "User-Agent: ${UA}"
)

TOTAL_COUNT=0
OK_COUNT=0

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

# Helper: faz GET silencioso e devolve só Content-Length e content-type
probe_head() {
  local group="$1"; shift
  local url="$1"; shift
  TOTAL_COUNT=$((TOTAL_COUNT + 1))
  printf '[%02d] %-12s HEAD %s\n' "${TOTAL_COUNT}" "${group}" "${url}" 1>&2
  echo "=== [${group}] HEAD ${url} ==="
  curl -sS -I --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" "$@" "${url}" 2>&1 | head -20
  echo
  echo "=== END ==="
  echo
  OK_COUNT=$((OK_COUNT + 1))
}

{
  echo "================================================================"
  echo " SVBONY SC002 — Probe Fase 3 (arquivos + persistência)"
  echo " Data:    $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "================================================================"
} 1>&2

# ============================================================================
# 0. Tirar uma foto fresca para garantir um arquivo conhecido
# ============================================================================
{
  echo
  echo "----- Snapshot inicial (gera um arquivo fresco) -----"
} 1>&2
probe_get "snapshot" "http://${TARGET}/app/snapshot"
sleep 1

# Pega o nome do arquivo mais recente do getfilelist (assumimos que vai
# estar em event/ com timestamp mais recente).
{
  echo
  echo "----- getfilelist depois do snapshot -----"
} 1>&2
probe_get "filelist" "http://${TARGET}/app/getfilelist"

# ============================================================================
# 1. Descobrir como BAIXAR um arquivo
# Tentamos vários paths plausíveis. Usamos um arquivo SEMPRE existente:
# pega o JSON do filelist e extrai o primeiro name de event/.
# ============================================================================
{
  echo
  echo "----- Tentativas de DOWNLOAD de arquivo -----"
  echo "Vamos usar nome estático para reproducibilidade."
} 1>&2

# Pega o nome real do primeiro event do filelist
LATEST_PHOTO=$(curl -sS --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" \
  "http://${TARGET}/app/getfilelist" | \
  python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    for folder in d.get('info', []):
        if folder.get('folder') == 'event' and folder.get('files'):
            print(folder['files'][0]['name'])
            sys.exit()
except Exception:
    pass
print('EMMC/Photo/F/20260607182633.jpg')
" 2>/dev/null || echo "EMMC/Photo/F/20260607182633.jpg")

echo "LATEST_PHOTO = ${LATEST_PHOTO}" 1>&2

# Tentativas de path / endpoint
DOWNLOAD_PATHS=(
  "/${LATEST_PHOTO}"                                  # direto pelo lighttpd
  "/EMMC/${LATEST_PHOTO}"
  "/sd/${LATEST_PHOTO}"
  "/storage/${LATEST_PHOTO}"
  "/app/file?name=${LATEST_PHOTO}"
  "/app/download?name=${LATEST_PHOTO}"
  "/app/getfile?name=${LATEST_PHOTO}"
  "/app/getphoto?name=${LATEST_PHOTO}"
  "/app/getvideo?name=${LATEST_PHOTO}"
  "/app/getmedia?name=${LATEST_PHOTO}"
  "/app/getthumbnail?name=${LATEST_PHOTO}"
  "/cgi-bin/get_file?name=${LATEST_PHOTO}"
  "/cgi-bin/getfile.cgi?name=${LATEST_PHOTO}"
)
for p in "${DOWNLOAD_PATHS[@]}"; do
  # Usamos HEAD para não baixar bytes; basta saber se existe
  probe_head "download" "http://${TARGET}${p}"
done

# ============================================================================
# 2. Endpoint candidatos de DELETE com NOME INVÁLIDO (não destrutivo)
# ============================================================================
{
  echo
  echo "----- DELETE com nome inválido (NÃO apaga real) -----"
} 1>&2

INVALID_NAME="this-file-does-not-exist.zzz"
DELETE_PATHS=(
  "/app/delfile?name=${INVALID_NAME}"
  "/app/deletefile?name=${INVALID_NAME}"
  "/app/delete?name=${INVALID_NAME}"
  "/app/rmfile?name=${INVALID_NAME}"
  "/app/removefile?name=${INVALID_NAME}"
  "/app/unlink?name=${INVALID_NAME}"
  "/cgi-bin/delete.cgi?name=${INVALID_NAME}"
)
for p in "${DELETE_PATHS[@]}"; do
  probe_get "del-probe" "http://${TARGET}${p}"
done

# ============================================================================
# 3. Teste de persistência via WILDCARD
# Sets via Config.cgi retornam 200 mas /Config.cgi?...&property=Camera.Menu.X
# (sem wildcard) retorna body vazio. A persistência tem que ser checada
# relendo o wildcard Camera.Menu.* e procurando a chave.
# ============================================================================
{
  echo
  echo "----- PERSISTÊNCIA via wildcard -----"
  echo "Sequência: GET Camera.Menu.* (baseline), SET HDR=OFF, GET *, SET HDR=ON, GET *"
} 1>&2

probe_get "persist-w" "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.*"
probe_get "persist-w" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=Camera.Menu.HDR&value=OFF"
sleep 1
probe_get "persist-w" "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.*"
probe_get "persist-w" "http://${TARGET}/cgi-bin/Config.cgi?action=set&property=Camera.Menu.HDR&value=ON"
sleep 1
probe_get "persist-w" "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.*"

# ============================================================================
# 4. Varredura de nomes para /app/getparamvalue
# Tentamos os nomes EXATOS observados em Camera.Menu.*
# ============================================================================
{
  echo
  echo "----- Varredura getparamvalue com nomes reais -----"
} 1>&2

PARAM_NAMES=(
  HDR VideoRes LoopingVideo MTD PhotoBurst PowerOffDelay PowerSaving
  SoundIndicator SoundRecord SpotMeter StatusLights TVSystem UIMode
  UpsideDown VideoClipTime VoiceSwitch VolAdj DefMode LCDPower
  Q-SHOT Timelapse TimelapseTime VideoTimeLapse
  # Nomes plausíveis em snake_case (palpites)
  hdr video_res loop motion_detect
  # E nomes com underscore que o SDK pode usar internamente
  ParkMode EmergencyMode CycleRecord GSensor Mic
)
for n in "${PARAM_NAMES[@]}"; do
  probe_get "param" "http://${TARGET}/app/getparamvalue?name=${n}"
done

# ============================================================================
# Resumo
# ============================================================================
{
  echo
  echo "================================================================"
  echo " SUMMARY (Fase 3)"
  echo " Total requests:    ${TOTAL_COUNT}"
  echo " HTTP/TCP success:  ${OK_COUNT}"
  echo "================================================================"
} 1>&2

echo
echo "=== PROBE_END ==="
echo "total=${TOTAL_COUNT}"
echo "ok=${OK_COUNT}"
echo "latest_photo=${LATEST_PHOTO}"
