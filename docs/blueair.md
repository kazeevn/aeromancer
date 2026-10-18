# Blueair purifier

Optionally, the recorder also polls a Blueair Classic i-series purifier
(280i, 480i, 680i, ...) through Blueair's cloud, using
[blueair_api](https://github.com/dahlb/blueair_api). This is the one part
that needs packages (and Python 3.12+):

```sh
uv venv && uv pip install -e '.[blueair]'   # or: python3 -m venv .venv && .venv/bin/pip install -e '.[blueair]'
```

Put the Blueair app login in `~/.config/aeromancer/blueair.toml` (or pass
another file with `--blueair-config`), readable only by you (`chmod 600`):

```toml
username = "you@example.com"
password = "secret"
device = "Bedroom"  # optional: purifier name or uuid; default: the first one
```

With that file present, `run` and `record` poll the purifier every 5 minutes
next to the meter; `python3 -m aeromancer blueair` polls only the purifier.
The cloud keeps one point per 5 minutes, and after a gap the poller fetches
what it missed, up to a day back. Points are stored as `blueair_pm25`,
`blueair_pm10`, `blueair_pm1`, `blueair_voc`, `blueair_co2`,
`blueair_temperature`, `blueair_humidity`, `blueair_all_pollution` (whichever
the model has), and with the newest point also the purifier's settings:
`blueair_fan_speed` and `blueair_auto_mode` (1 when the fan follows the
sensors, 0 when it is set by hand). The cloud keeps no history of the
settings, so they are missing for any time the poller was down.

`blueair_co2` is recorded but not charted or analysed: it is an estimate
from the VOC sensor that doesn't follow real CO₂
([study](archive/blueair-eco2.md)). The same study found that the cloud
returns nothing older than 42 days, so anything older exists only in our
own recording.

For the systemd unit, point its `ExecStart` at
`%h/projects/aeromancer/.venv/bin/python3` so it finds the package.
