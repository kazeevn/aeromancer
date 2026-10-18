# Blueair purifier

Optionally, the recorder also polls a Blueair Classic i-series purifier
(280i, 480i, 680i, ...) through Blueair's cloud, using
[blueair_api](https://github.com/dahlb/blueair_api), which comes in the
`blueair` extra (and needs Python 3.12+):

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

## Filter

The cloud reports no filter age or date. The app's "Filter: N days left"
for a Classic purifier comes from a usage counter, read from the app's
code (version 4.11.0):

- The `fan_usage` attribute holds six `;`-separated counters of 5-minute
  ticks, e.g. `40;5200;1100;1900;8200;41000`.
- The fifth (`8200`) counts the time the filter has run since it was last
  reset in the app, which sets it back to 0. It counts running time only:
  time the purifier is unplugged or offline doesn't count.
- The app shows `180 - floor(ticks * 5 / 1444)` days left (here 152), and
  the filter as used up after 180 days of running. The fan speed doesn't
  matter, and nothing measures the filter's condition.
- The first four look like the ticks at each fan speed since the reset: they
  add up to about the fifth. What the sixth counts is unknown.
- The cloud updates the counters rarely: they stood still over 15 minutes
  of running.

The poller stores the six as `blueair_fan_usage_0` to `blueair_fan_usage_5`,
and `filter_status` (`OK` or not) as `blueair_filter_expired` (0 or 1). When
the fifth counter goes down, it also stores `blueair_filter_replaced` (1),
put as many ticks of running before that upload as the counter shows, but
not before the previous upload.

## Filter health

The app's timer is blind to what the filter caught. A decay test measures
it instead: how fast the purifier at speed 1 clears a room filled with
particles, against what a fresh filter would do. The dashboard's Filter tile
shows the last test and a forecast.

**The test.** With haze outside (or another particle source), in the room
the purifier stands in:

1. Close the room's doors (and wardrobes), set the fan to 0 in the app, and
   open the window for about 20 minutes.
2. Close the window, set the fan to speed 1, and leave the room closed for
   an hour.
3. Set the purifier back to auto.

The recording holds the rest: the test is found by the fan set by hand to 0
and then by hand to speed 1 for 40 minutes or more. The first 10 minutes at
speed 1 are left out (the room is still mixing), and the rest is fitted with
`C(t) = C_ss + A exp(-rate t)`. Then

    health = (rate - background) * room_volume / cadr

is the filter's clean air delivery as a share of a fresh one's: 1 new, 0.5
due (the end of life GB/T 18801 uses). `background` is the loss to leaks and
walls alone. The purifier can't measure it: with the fan off its sensor
reads its own pocket of air, not the room (it fell from 35 to 5 µg/m³ in
five minutes with the window shut, then rose slowly after it was opened). So
it is taken as a range, 0.3–1 /h by default, which moves the health by
about ±0.1 when a fresh filter clears 4–5 /h.

The forecast assumes the filter wears with age, `health = exp(-age / tau)`,
and fits `1 / tau` to the tests since the replacement (the latest
`blueair_filter_replaced`, or else as long ago as the filter counter has
run). Its range is the 90 % one. One test fixes `tau` only loosely; repeat it
every few weeks, and after haze. If the health falls faster in haze than
between, it goes with what the filter caught, not its age, and the forecast
is too late.

The room and the purifier's figures go in the purifier's config:

```toml
[filter]
room_volume = 30.0   # m³ of air in the closed room, closed furniture taken out
cadr = 100.0         # m³/h, a fresh filter's clean air delivery at speed 1
# cadr_error = 0.15  # how far off cadr may be, relative
# background = [0.3, 1.0]  # /h, the loss with the fan off
# replace_at = 0.5   # health at which the filter is due
```

For `cadr`, Blueair lists the airflow at each speed and the clean air
delivery (CADR) at the top one only; their ratio at the top speed (about
0.8) times the airflow at speed 1 is a fair guess. Without the table the
tile shows the decay rate and the app's timer only.

`blueair_co2` is recorded but not charted or analysed: it is an estimate
from the VOC sensor that doesn't follow real CO₂
([study](archive/blueair-eco2.md)). The same study found that the cloud
returns nothing older than 42 days, so anything older exists only in our
own recording.

For the systemd unit, point its `ExecStart` at
`%h/projects/aeromancer/.venv/bin/python3` so it finds the package.
