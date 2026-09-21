#!/usr/bin/env bash
set -euo pipefail

usage(){ cat <<'EOF'
Usage: sudo ./install.sh --device /dev/serial/by-id/YOUR_ADAPTER [options]
  --gateway-port PORT   Raw TCP port for Home Assistant (default: 4196)
  --web-port PORT       WebUI port (default: 8080)
  --enable-onewire      Install optional DS18B20/Pi diagnostics service
EOF
}
device=""; gateway_port=4196; web_port=8080; onewire=0
while [[ $# -gt 0 ]]; do case "$1" in
  --device) device=${2:-}; shift 2;; --gateway-port) gateway_port=${2:-}; shift 2;;
  --web-port) web_port=${2:-}; shift 2;; --enable-onewire) onewire=1; shift;;
  -h|--help) usage; exit 0;; *) usage >&2; exit 2;; esac; done
[[ ${EUID} -eq 0 ]] || { echo "Run as root with sudo." >&2; exit 1; }
[[ ${device} == /dev/serial/by-id/* ]] || { echo "Use a stable /dev/serial/by-id/... path." >&2; exit 2; }
[[ ${gateway_port} =~ ^[0-9]+$ && ${web_port} =~ ^[0-9]+$ ]] || { echo "Ports must be numeric." >&2; exit 2; }
command -v apt-get >/dev/null || { echo "This installer supports Raspberry Pi OS, Debian and Ubuntu (apt)." >&2; exit 1; }

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
temp_dir=""
if [[ ! -f ${source_dir}/gateway/dashboard_server.py ]]; then
  temp_dir=$(mktemp -d); trap '[[ -n ${temp_dir} ]] && rm -rf -- "${temp_dir}"' EXIT
  release_url=$(curl -fsSL https://api.github.com/repos/MRDonnii/dantherm-hch-passivelink-webui/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tarball_url"])')
  curl -fsSL "${release_url}" | tar -xz -C "${temp_dir}" --strip-components=1
  source_dir=${temp_dir}
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip curl
if ! id passivelink-webui >/dev/null 2>&1; then useradd --system --home /opt/dantherm-passivelink-webui --shell /usr/sbin/nologin --groups dialout,video passivelink-webui; else usermod -aG dialout,video passivelink-webui; fi
install -d -o passivelink-webui -g passivelink-webui /opt/dantherm-passivelink-webui
install -d -o root -g passivelink-webui -m 0750 /etc/dantherm-passivelink-webui
backup="/var/backups/dantherm-webui-$(date +%Y%m%d-%H%M%S)"; install -d -m 0700 "${backup}"
for path in /etc/dantherm-passivelink-webui/gateway.env /etc/dantherm-passivelink-webui/onewire.json; do [[ -e ${path} ]] && cp -a "${path}" "${backup}/"; done
install -o passivelink-webui -g passivelink-webui -m 0755 "${source_dir}"/gateway/*.py /opt/dantherm-passivelink-webui/
install -d -o passivelink-webui -g passivelink-webui /opt/dantherm-passivelink-webui/webui
install -o passivelink-webui -g passivelink-webui -m 0644 "${source_dir}"/gateway/webui/* /opt/dantherm-passivelink-webui/webui/
if [[ ! -x /opt/dantherm-passivelink-webui/venv/bin/python ]]; then runuser -u passivelink-webui -- python3 -m venv /opt/dantherm-passivelink-webui/venv; fi
runuser -u passivelink-webui -- /opt/dantherm-passivelink-webui/venv/bin/pip install --upgrade pip
runuser -u passivelink-webui -- /opt/dantherm-passivelink-webui/venv/bin/pip install pyserial==3.5
token=$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')
[[ -f /etc/dantherm-passivelink-webui/gateway.env ]] && token=$(sed -n 's/^DANTHERM_REBOOT_TOKEN=//p' /etc/dantherm-passivelink-webui/gateway.env | head -1)
cat > /etc/dantherm-passivelink-webui/gateway.env <<EOF
RS485_DEVICE=${device}
GATEWAY_BIND=0.0.0.0
GATEWAY_PORT=${gateway_port}
WEBUI_BIND=0.0.0.0
WEBUI_PORT=${web_port}
DANTHERM_REBOOT_TOKEN=${token}
DANTHERM_ADMIN_URL=http://127.0.0.1:4198
EOF
[[ ${onewire} -eq 1 ]] && echo 'ONEWIRE_URL=http://127.0.0.1:4197/temperatures' >> /etc/dantherm-passivelink-webui/gateway.env
chown root:passivelink-webui /etc/dantherm-passivelink-webui/gateway.env; chmod 0640 /etc/dantherm-passivelink-webui/gateway.env
if [[ ! -f /etc/dantherm-passivelink-webui/onewire.json ]]; then install -o root -g passivelink-webui -m 0640 "${source_dir}/gateway/onewire.example.json" /etc/dantherm-passivelink-webui/onewire.json; fi
install -o root -g root -m 0644 "${source_dir}/systemd/dantherm-webui-gateway.service" /etc/systemd/system/
install -o root -g root -m 0644 "${source_dir}/systemd/dantherm-webui-admin.service" /etc/systemd/system/
install -d /opt/dantherm-webui
install -o root -g root -m 0755 "${source_dir}/gateway/dantherm_pi_admin_api.py" /opt/dantherm-webui/dantherm_pi_admin_api.py
install -o root -g root -m 0644 "${source_dir}/gateway/diagnostics_report.py" /opt/dantherm-webui/diagnostics_report.py
install -d -m 0750 /etc/dantherm-webui
cat > /etc/dantherm-webui/admin.env <<EOF
DANTHERM_REBOOT_TOKEN=${token}
DANTHERM_ADMIN_BIND=127.0.0.1
DANTHERM_ADMIN_PORT=4198
DANTHERM_GATEWAY_SERVICE=dantherm-webui-gateway.service
DANTHERM_ONEWIRE_SERVICE=dantherm-webui-onewire.service
EOF
chmod 0600 /etc/dantherm-webui/admin.env
if [[ ${onewire} -eq 1 ]]; then install -m 0644 "${source_dir}/systemd/dantherm-webui-onewire.service" /etc/systemd/system/; fi
systemctl daemon-reload
systemctl enable --now dantherm-webui-admin.service dantherm-webui-gateway.service
[[ ${onewire} -eq 1 ]] && systemctl enable --now dantherm-webui-onewire.service
systemctl restart dantherm-webui-admin.service dantherm-webui-gateway.service
echo "Installed. Open http://$(hostname -I | awk '{print $1}'):${web_port}/ and create the first owner."
echo "Home Assistant: RS485 over TCP, host $(hostname -I | awk '{print $1}'), port ${gateway_port}."
echo "Rollback backup: ${backup}"
