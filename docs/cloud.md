# Hosting

To record from more than one computer, and to show the dashboard to other
people, aeromancer can run on a free-tier Google Compute Engine VM:

```
laptop ─ record ─ its own SQLite ─ upload every 30 s ──HTTPS──┐
laptop ─ record ─ its own SQLite ─ upload every 30 s ──HTTPS──┤
                                                               ▼
people ─ share link ──HTTPS──▶ Caddy ──▶ aeromancer host ──▶ SQLite on the VM
                                         + the NEA, weather, pressure, Blueair and Google Health pollers
```

The machine with the meter keeps recording into its own database, so it
records on while offline, and uploads what the meter said since its last
upload ([push.py](../aeromancer/push.py)). Only the meter's quantities go up
(`co2`, `temperature`, `humidity`, `op_*`); the VM polls everything else
itself, around the clock. The server skips readings it already has, so a
retried upload or a second machine's backlog does no harm.

Everyone needs a token ([tokens.py](../aeromancer/tokens.py)), and each
token has an expiry date and can be revoked. A `view` token opens the
dashboard: its link `https://…/?t=aer_…` turns into a cookie that lasts until
the token expires, so the people you share it with don't log in. A `write`
token is for one recording machine: it uploads readings and records device
moves, and can't open the dashboard. The database stores only each token's
hash.

## Cost

The e2-micro VM, its 30 GB standard disk and 1 GB a month of traffic out are
in Google's always-free tier, in `us-west1`, `us-central1` or `us-east1`. The
public IPv4 address isn't: about $3.65 a month. Traffic beyond 1 GB costs
about $0.12/GB. An open dashboard tab uses about 9 MB an hour, compressed, and
a hidden tab stops refreshing. Daily snapshots, kept a week, cost cents.

Why a VM and not Cloud Run with a managed database: Cloud SQL has no free
tier, Firestore can't aggregate into chart buckets, and BigQuery takes about
a second per query. One SQLite file next to the code does all of this in
milliseconds.

## Setup

Once, with `gcloud` logged in and the project chosen:

```sh
gcloud billing projects link PROJECT --billing-account ACCOUNT   # the free tier needs billing on
deploy/gce.sh create   # the VM, a static address, the firewall rule for 80 and 443, daily snapshots
deploy/gce.sh deploy   # this checkout; installs Caddy and the packages, and prints the address
deploy/gce.sh config   # the pollers' config files from ~/.config/aeromancer
deploy/gce.sh db       # optional: start from this machine's database
```

The address is `https://1-2-3-4.sslip.io`, named after the VM's IP, and
Caddy gets its certificate from Let's Encrypt. `AEROMANCER_VM` and
`AEROMANCER_ZONE` choose another VM name or zone (default `aeromancer` in
`us-west1-b`).

A budget alert costs nothing and catches surprises. Give the amount in the
billing account's currency (`gcloud billing accounts describe ACCOUNT`), e.g.
`7SGD`, or the request is refused as an invalid argument:

```sh
gcloud services enable billingbudgets.googleapis.com
gcloud billing budgets create --billing-account ACCOUNT --display-name aeromancer \
    --budget-amount 5USD --threshold-rule percent=0.5 --threshold-rule percent=1.0
```

## Sharing the dashboard

```sh
deploy/gce.sh token add alice --for 7d    # prints the link to send
deploy/gce.sh token add me --for never    # your own
deploy/gce.sh token list
deploy/gce.sh token revoke 3              # stops working at once
```

Add a section to the link, `…/?t=aer_…#tree-of-life`, to open the
dashboard there.

## Recording from a computer

Issue it a write token, and put the address and the token in
`~/.config/aeromancer/remote.toml` on that computer, readable only by you:

```sh
deploy/gce.sh token add laptop --write --for never
```

```toml
url = "https://1-2-3-4.sslip.io"
token = "aer_..."
```

Then `run` and `record` upload as they record, and `place`, `placements` and
`unplace` act on the server's database. Nothing else changes: the local
dashboard still shows the local database.

## Upkeep

- Updating: `deploy/gce.sh deploy` uploads this checkout as it is, and
  restarts.
- Google Health: after each `health-login` (weekly, while the OAuth app is in
  Testing; see [health.md](health.md)), `deploy/gce.sh health-token`.
- Logs: `deploy/gce.sh ssh journalctl -u aeromancer-host@\$USER -f`.
- Debian installs its security updates by itself (`unattended-upgrades`).
