#!/usr/bin/env bash
TARGET="${TARGET:-192.168.0.1}"
UA='HSMSCAM2/1.9.1 (iPad; iOS 26.6; Scale/2.00)'
HDRS=(-H "Host: ${TARGET}" -H 'Accept: */*'
      -H 'Accept-Language: pt-BR;q=1, en-BR;q=0.9, es-419;q=0.8'
      -H 'Connection: keep-alive' -H 'Accept-Encoding: gzip, deflate'
      -H "User-Agent: ${UA}")

URLS=(
  "http://${TARGET}/cgi-bin/hisnet/getdeviceattr.cgi?"
  "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Preview.*"
  "http://${TARGET}/cgi-bin/Config.cgi?action=get&property=Camera.Menu.*"
  "http://${TARGET}/app/getbatteryinfo"
  "http://${TARGET}/app/getsnapinfo"
)

while true; do
  for u in "${URLS[@]}"; do
    curl -sS -o /dev/null -w '%{http_code} %{url_effective}\n' \
         --http1.1 "${HDRS[@]}" "$u"
    sleep 0.5
  done
done