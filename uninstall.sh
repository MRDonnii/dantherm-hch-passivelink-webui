#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 1; }
echo "This stops and removes the WebUI services and program files. Configuration and history are preserved."
read -r -p "Continue? [y/N] " answer; [[ ${answer,,} == y ]] || exit 0
systemctl disable --now dantherm-webui-gateway.service dantherm-webui-admin.service dantherm-webui-onewire.service 2>/dev/null || true
for unit in dantherm-webui-gateway.service dantherm-webui-admin.service dantherm-webui-onewire.service; do [[ -e /etc/systemd/system/${unit} ]] && unlink "/etc/systemd/system/${unit}"; done
systemctl daemon-reload
echo "Program files can now be removed from /opt/dantherm-passivelink-webui and /opt/dantherm-webui."
echo "Preserved: /etc/dantherm-passivelink-webui and /var/lib/dantherm-hch5-ha."
