#!/bin/bash
# Runs the hosted dashboard on a free-tier Compute Engine VM (docs/cloud.md). Uses gcloud's default project.
#
#   deploy/gce.sh create              the VM, its address, firewall rule and daily snapshots (once)
#   deploy/gce.sh deploy              upload this checkout and (re)start it
#   deploy/gce.sh config              copy the pollers' config files from ~/.config/aeromancer
#   deploy/gce.sh health-token        copy only the Google Health login, after health-login
#   deploy/gce.sh db                  replace the VM's database with a copy of this machine's
#   deploy/gce.sh token ARGS...       aeromancer token ARGS... on the VM, e.g. token add alice --for 7d
#   deploy/gce.sh ssh [COMMAND]
set -euo pipefail

VM=${AEROMANCER_VM:-aeromancer}
ZONE=${AEROMANCER_ZONE:-us-west1-b}  # e2-micro is free in us-west1, us-central1 and us-east1; west is nearest Asia
REGION=${ZONE%-*}
CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}/aeromancer
DB=${XDG_DATA_HOME:-$HOME/.local/share}/aeromancer/readings.sqlite3
REPO=$(cd "$(dirname "$0")/.." && pwd)

on_vm() { gcloud compute ssh "$VM" --zone "$ZONE" --command "$1"; }
local_zone() {  # this machine's time zone, as a tz database name, or nothing
    local zone
    zone=$(timedatectl show -p Timezone --value 2>/dev/null) || true
    [ -n "$zone" ] || zone=$(readlink /etc/localtime 2>/dev/null | sed -n 's|.*/zoneinfo/||p')
    echo "$zone"
}
copy_to_vm() {  # files... destination-directory
    local dest=${*: -1}
    on_vm "mkdir -p $dest"
    gcloud compute scp --zone "$ZONE" --compress "${@:1:$#-1}" "$VM:$dest/"
}

case ${1:-} in
create)
    gcloud services enable compute.googleapis.com
    gcloud compute addresses create "$VM" --region "$REGION"
    gcloud compute firewall-rules create aeromancer-web --allow tcp:80,tcp:443 --target-tags aeromancer
    gcloud compute resource-policies create snapshot-schedule aeromancer-daily \
        --region "$REGION" --daily-schedule --start-time 20:00 --max-retention-days 7
    gcloud compute instances create "$VM" --zone "$ZONE" --machine-type e2-micro \
        --image-family debian-13 --image-project debian-cloud \
        --boot-disk-size 30GB --boot-disk-type pd-standard \
        --address "$VM" --tags aeromancer
    gcloud compute disks add-resource-policies "$VM" --zone "$ZONE" --resource-policies aeromancer-daily
    ;;
deploy)
    # This checkout as it is, committed or not, without what git ignores (the venv, databases),
    # and this machine's time zone, so that the times the dashboard writes out read as at home.
    git -C "$REPO" status --short | grep -q . && echo "deploying uncommitted changes" >&2
    git -C "$REPO" ls-files -z --cached --others --exclude-standard |
        tar -C "$REPO" --null --files-from - --ignore-failed-read -cz |
        gcloud compute ssh "$VM" --zone "$ZONE" --command \
            "rm -rf ~/aeromancer/src && mkdir -p ~/aeromancer/src && tar -xz -C ~/aeromancer/src && ~/aeromancer/src/deploy/setup-vm.sh $(printf %q "$(local_zone)")"
    ;;
config)
    files=()
    for f in nea.toml blueair.toml zytemp.toml google-health-client.json google-health-token.json; do
        [ -e "$CONFIG/$f" ] && files+=("$CONFIG/$f")
    done
    copy_to_vm "${files[@]}" .config/aeromancer
    on_vm 'chmod 600 ~/.config/aeromancer/* && sudo systemctl restart aeromancer-host@$USER'
    ;;
health-token)
    copy_to_vm "$CONFIG/google-health-token.json" .config/aeromancer  # the running poller picks it up
    on_vm 'chmod 600 ~/.config/aeromancer/google-health-token.json'
    ;;
db)
    # A consistent copy while the recorder runs; the uploads from here then fill in what came after.
    copy=$(mktemp --suffix .sqlite3)
    trap 'rm -f "$copy"' EXIT
    python3 -c 'import sqlite3, sys; sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True).backup(sqlite3.connect(sys.argv[2]))' \
        "$DB" "$copy"
    copy_to_vm "$copy" .local/share/aeromancer
    on_vm "sudo systemctl stop aeromancer-host@\$USER && cd ~/.local/share/aeromancer &&
        rm -f readings.sqlite3-wal readings.sqlite3-shm && mv $(basename "$copy") readings.sqlite3 &&
        sudo systemctl start aeromancer-host@\$USER"
    ;;
token)
    shift
    on_vm "cd ~/aeromancer/src && ../venv/bin/python -m aeromancer token $(printf '%q ' "$@")"
    ;;
ssh)
    shift
    if [ $# -gt 0 ]; then on_vm "$*"; else gcloud compute ssh "$VM" --zone "$ZONE"; fi
    ;;
*)
    sed -n '2,11s/^# \{0,1\}//p' "$0"
    exit 1
    ;;
esac
