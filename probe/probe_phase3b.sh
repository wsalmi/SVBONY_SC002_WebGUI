#!/usr/bin/env bash
# probe_phase3b.sh - Fase 3b: APENAS download direto de arquivo.
#
# No Fase 3 a câmera desconectou durante os 8 primeiros requests (curl exit 7).
# Esse probe é curto (~15s) e focado SÓ nos paths de download que perdemos.
#
# Antes de rodar:
#   1. Confirme que está conectado no SSID SC002_XXXX
#   2. Tente abrir http://192.168.0.1/app/getbatteryinfo no navegador
#      (se voltar JSON, está pronto)
#
# Uso:
#   bash probe/probe_phase3b.sh > probe/probe_phase3b_results.txt 2>&1

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

TOTAL=0; OK=0
probe_head() {
  local group="$1"; shift
  local url="$1"; shift
  TOTAL=$((TOTAL + 1))
  printf '[%02d] %-10s HEAD %s\n' "${TOTAL}" "${group}" "${url}" 1>&2
  echo "=== [${group}] HEAD ${url} ==="
  curl -sS -I --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" "$@" "${url}" 2>&1 | head -15
  echo
  echo "=== END ==="
  echo
  OK=$((OK + 1))
}

probe_range() {
  # GET com Range: bytes=0-31 — pega só 32 bytes (magic bytes JPEG/MP4)
  local group="$1"; shift
  local url="$1"; shift
  TOTAL=$((TOTAL + 1))
  printf '[%02d] %-10s GET-32B %s\n' "${TOTAL}" "${group}" "${url}" 1>&2
  echo "=== [${group}] GET (Range: bytes=0-31) ${url} ==="
  curl -sS -i --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" \
    -H 'Range: bytes=0-31' "${url}" 2>&1 | head -25 | \
    perl -pe 's/[\x00-\x08\x0e-\x1f\x7f]/./g'
  echo
  echo "=== END ==="
  echo
  OK=$((OK + 1))
}

{
  echo "================================================================"
  echo " SVBONY SC002 — Probe Fase 3b (download retry)"
  echo " Data:    $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "================================================================"
  echo
  echo "----- Sanity check (conexão) -----"
} 1>&2

echo "=== sanity ===" 
curl -sS --max-time 3 "${HDRS[@]}" "http://${TARGET}/app/getbatteryinfo" || echo "OFFLINE"
echo
echo "==="

# Pega arquivo real do filelist
LATEST=$(curl -sS --http1.1 --max-time "${TIMEOUT}" "${HDRS[@]}" \
  "http://${TARGET}/app/getfilelist" 2>/dev/null | \
  python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    for folder in d.get('info', []):
        if folder.get('folder') == 'event' and folder.get('files'):
            print(folder['files'][0]['name']); sys.exit()
    for folder in d.get('info', []):
        if folder.get('files'):
            print(folder['files'][0]['name']); sys.exit()
except Exception:
    pass
print('EMMC/Photo/F/20260607182633.jpg')
" 2>/dev/null || echo "EMMC/Photo/F/20260607182633.jpg")

echo "LATEST = ${LATEST}" 1>&2

# ============================================================================
# Tentativas de DOWNLOAD DIRETO (paths que o Fase 3 perdeu)
# ============================================================================
{
  echo
  echo "----- Direct EMMC paths (lighttpd serve estático?) -----"
} 1>&2

# Mais paths possíveis baseados em diferentes layouts de SDKs
DOWNLOAD_PATHS=(
  # Path direto do JSON (raiz)
  "/${LATEST}"
  # Variantes com prefixo
  "/EMMC/${LATEST}"
  "/sd/${LATEST}"
  "/mnt/${LATEST}"
  "/mmc/${LATEST}"
  "/data/${LATEST}"
  "/storage/${LATEST}"
  "/cgi/${LATEST}"
  "/files/${LATEST}"
  "/dav/${LATEST}"
  # Query-style
  "/app/file?name=${LATEST}"
  "/app/download?name=${LATEST}"
  "/app/getfile?name=${LATEST}"
  "/app/get?name=${LATEST}"
  "/app/getmedia?name=${LATEST}"
  "/app/media?name=${LATEST}"
  "/app/loadfile?name=${LATEST}"
  "/app/readfile?name=${LATEST}"
  # Sem o prefixo EMMC (talvez o servidor entenda só o sufixo)
  "/${LATEST#EMMC/}"
  "/Photo/F/$(basename ${LATEST})"
)
for p in "${DOWNLOAD_PATHS[@]}"; do
  probe_head "dl-head" "http://${TARGET}${p}"
done

# Para todo HEAD que deu 200 OK, fazer GET range para ver magic bytes
{
  echo
  echo "----- Magic bytes (Range 0-31) nos paths /app/getthumbnail e /app/snapshot -----"
} 1>&2

# getthumbnail com path real — Fase 3 confirmou 200 OK, agora vê os bytes
probe_range "thumb" "http://${TARGET}/app/getthumbnail?name=${LATEST}"

# Por garantia: tenta endpoint que combina /app/ com path direto
probe_range "dl-byte" "http://${TARGET}/${LATEST}"
probe_range "dl-byte" "http://${TARGET}/EMMC/${LATEST}"
probe_range "dl-byte" "http://${TARGET}/sd/${LATEST}"

# ============================================================================
# Resumo
# ============================================================================
{
  echo
  echo "================================================================"
  echo " SUMMARY (Fase 3b)"
  echo " Total requests:    ${TOTAL}"
  echo " HTTP/TCP success:  ${OK}"
  echo "================================================================"
} 1>&2

echo
echo "=== PROBE_END ==="
echo "total=${TOTAL}"
echo "ok=${OK}"
echo "latest=${LATEST}"
