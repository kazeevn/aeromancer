# Blueair purifier

Optionally, the recorder also polls a Blueair Classic i-series purifier
(280i, 480i, 680i, ...) through Blueair's cloud, using
[blueair_api](https://github.com/dahlb/blueair_api), which comes in the
`blueair` extra (and needs Python 3.12+):

```sh
uv sync --extra blueair   # or: python3 -m venv .venv && .venv/bin/pip install -e '.[blueair]'
```

Put the Blueair app login in `~/.config/aeromancer/blueair.toml` (or pass
another file with `--blueair-config`), readable only by you (`chmod 600`):

```toml
username = "you@example.com"
password = "secret"
device = "Bedroom"  # optional: purifier name or uuid; default: the first one
```

With that file present, `run` and `record` poll the purifier every 5 minutes
next to the meter; `uv run aeromancer blueair` polls only the purifier.
The cloud keeps one point per 5 minutes, and after a gap the poller fetches
what it missed, up to a day back. Points are stored as `blueair_pm25`,
`blueair_pm10`, `blueair_pm1`, `blueair_voc`, `blueair_co2`,
`blueair_temperature`, `blueair_humidity`, `blueair_all_pollution` (whichever
the model has), and with the newest point also the purifier's settings:
`blueair_fan_speed` and `blueair_auto_mode` (1 when the fan follows the
sensors, 0 when it is set by hand). The cloud keeps no history of the
settings, so they are missing for any time the poller was down.

## Settings

`purifier` shows the purifier's settings, its filter and its latest upload,
and changes the settings through the same cloud as the app:

```sh
uv run aeromancer purifier                  # show only
uv run aeromancer purifier --fan 1          # a speed, 0 to 3, set by hand
uv run aeromancer purifier --fan auto       # back to following its sensors
uv run aeromancer purifier --brightness 0 --lock on   # lights off, buttons locked
```

The poller records a changed fan speed or mode with the next upload, up to
5 minutes later.

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
shows the last test and two forecasts.

**The test.** With haze outside (or another particle source), in the room
the purifier stands in:

1. Close the room's doors (and wardrobes), set the fan to 0 (in the app, or
   `purifier --fan 0`), and open the window for about 20 minutes.
2. Close the window, set the fan to speed 1 (`purifier --fan 1`), and leave
   the room closed for an hour.
3. Set the purifier back to auto (`purifier --fan auto`).

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

There are two forecasts, each fitted to the tests since the replacement (the
latest `blueair_filter_replaced`, or else as long ago as the filter counter
has run), each with its 90 % range:

- **By age**: `health = exp(-age / tau)`. Charge on the filter's fibres
  fades with time, faster in humid air, whatever the air carried.
- **By what it caught**: `health = exp(-caught / m0)`, `caught` being the
  particles a fresh filter would have taken from the air the purifier
  moved: each upload's PM2.5 × the fresh clean air delivery at the fan's
  speed × the time to the next upload. It goes on at the last week's pace,
  so it comes earlier in haze and later in clean air. (At the average pace
  since the replacement it would be the age forecast again.) Uploads with
  no recorded speed take auto mode's: speed 1 below 23.5 µg/m³, 2 below
  33.5, else 3 (it matched the recorded speed 91 % of a day).

One test fits both equally well. Repeat it every few weeks, and after haze:
if the health falls faster across haze than across clean air, it goes with
what the filter caught.

The room and the purifier's figures go in the purifier's config:

```toml
[filter]
room_volume = 30.0   # m³ of air in the closed room, closed furniture taken out
cadr = 100.0         # m³/h, a fresh filter's clean air delivery at speed 1
# cadr_error = 0.15  # how far off cadr may be, relative
# background = [0.3, 1.0]  # /h, the loss with the fan off
# replace_at = 0.5   # health at which the filter is due
airflow = [130, 260, 520]  # m³/h at speeds 1, 2, 3, for the forecast by what it caught
```

For `cadr`, Blueair lists the airflow at the lowest and the highest speed,
and the clean air delivery (CADR) at the highest only; their ratio there
(about 0.8) times the airflow at speed 1 is a fair guess. Speed 2's airflow
can be put between the two. Without the table the tile shows the decay rate
and the app's timer only; without `airflow`, only the forecast by age.

`blueair_co2` is recorded but not charted or analysed: it is an estimate
from the VOC sensor that doesn't follow real CO₂
([study](archive/blueair-eco2.md)). The same study found that the cloud
returns nothing older than 42 days, so anything older exists only in our
own recording.

`blueair_temperature` reads warm from the purifier's own heat: about 0.9 °C
above the zyTemp with the fan off and 2–4 °C running, more at low speed
([study](archive/blueair-temperature.md)).

## Outdoor intake

The purifier can be set up to take its air mostly from outside
(`place blueair ... --outdoor-intake`, [placements](recording.md#where-the-devices-are)).
It then works as a filtered fresh-air supply: it draws outside air through
the filter and blows it into the room, and the air it pushes in leaves
through the room's other gaps. So:

- Its PM, VOC, temperature and humidity are the outside air's (the
  temperature still warmed by its own fan), on the charts against NEA's.
  Nothing records the room's particles meanwhile. The divinations leave
  these readings out: the ward goes quiet over that time, and the house's
  chord and the Tree of Life read the house from the meter alone.
- The room gets more air changes, so its CO₂ stays nearer outdoor's
  (about 420 ppm) and falls back faster once people leave. Souls present
  fits the air changes to each window's CO₂, so it follows, but a window
  across the change mixes the two.
- No decay test is found while it lasts: the purifier no longer clears the
  room it reads.
- The forecast by what the filter caught gets better: the PM2.5 it reads is
  what goes through the filter, where in a room it is what the purifier
  leaves behind.

For the systemd unit, point its `ExecStart` at
`%h/projects/aeromancer/.venv/bin/python3` so it finds the package.
