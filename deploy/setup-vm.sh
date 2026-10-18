#!/bin/bash
# Runs on the VM, from the unpacked source (deploy/gce.sh deploy): installs what aeromancer needs, and (re)starts it.
# Takes the deploying machine's time zone, if any, for the clock times the server writes out (the VM's is UTC).
set -euo pipefail
src=$(cd "$(dirname "$0")/.." && pwd)
base=$(dirname "$src")
zone=${1:-}

if [ -n "$zone" ] && [ "$(timedatectl show -p Timezone --value)" != "$zone" ]; then
    sudo timedatectl set-timezone "$zone" || echo "could not set the time zone to $zone" >&2
fi

if ! command -v caddy >/dev/null; then
    sudo apt-get update -q
    sudo apt-get install -y -q caddy python3-venv unattended-upgrades
fi
if ! grep -q /swapfile /proc/swaps; then  # 1 GB of RAM is tight for numpy and scipy
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

if [ ! -x "$base/uv/bin/uv" ]; then
    python3 -m venv "$base/uv"
    "$base/uv/bin/pip" install -q uv
fi
UV_PROJECT_ENVIRONMENT="$base/venv" "$base/uv/bin/uv" sync -q --frozen --no-dev --extra blueair --project "$src"

ip=$(curl -sf -H Metadata-Flavor:Google \
    http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
host="${ip//./-}.sslip.io"
sed "s/{\$AEROMANCER_HOST}/$host/" "$src/deploy/Caddyfile" | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl reload-or-restart caddy
mkdir -p ~/.config/aeromancer
printf 'url = "https://%s"\n' "$host" >~/.config/aeromancer/host.toml

sudo cp "$src/deploy/aeromancer-host@.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable -q "aeromancer-host@$USER"
sudo systemctl restart "aeromancer-host@$USER"
echo "serving https://$host"
