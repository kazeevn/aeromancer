# aeromancer

Records the ZyAura / Holtek "USB-zyTemp" CO₂ meter (USB `04d9:a052`), stores
the readings in SQLite, draws them on a local dashboard, and runs a
strictly pseudo-scientific analysis of your air.

Pure Python standard library (3.11+): no packages to install, unless you
also want the optional Blueair purifier poller.

## Setup

Let your user read the meter (once):

```sh
sudo install -m644 udev/70-aeromancer.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw
```

## Usage

```sh
python3 -m aeromancer run            # record + dashboard at http://127.0.0.1:8000
python3 -m aeromancer record         # record only
python3 -m aeromancer serve          # dashboard only (reads the same database)
python3 -m aeromancer oracle --range 7d   # the analysis, in the terminal
```

`run` and `serve` listen on localhost only; add `--public` to serve the
dashboard on all interfaces, e.g. to read it from your phone. It has no
login, so anyone on the network can see it.

Readings go to `~/.local/share/aeromancer/readings.sqlite3` (override with
`--db`), at most one per quantity every 5 s (`--min-interval`). A database at
the pre-rename location, `~/.local/share/co2monitor/`, is still used if it is
the only one. The recorder survives the meter being unplugged and picks it up
again.

To record all the time, as a systemd user service:

```sh
cp systemd/aeromancer.service ~/.config/systemd/user/
systemctl --user enable --now aeromancer
```

To try the dashboard without the meter:

```sh
python3 -m aeromancer --db /tmp/demo.sqlite3 simulate --days 14
python3 -m aeromancer --db /tmp/demo.sqlite3 serve
```

## Blueair purifier

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

For the systemd unit, point its `ExecStart` at
`%h/projects/co2-monitor/.venv/bin/python3` so it finds the package.

## Outdoor PM2.5 and weather (Singapore)

Optionally, the recorder also fetches the outdoor PM2.5 that NEA measures,
from [data.gov.sg](https://guide.data.gov.sg/developer-guide/real-time-apis).
This is free, needs no key, and uses the standard library only. Name your
region (`north`, `south`, `east`, `west` or `central`; see NEA's list of
towns per region) in `~/.config/aeromancer/nea.toml`, or pass another file
with `--nea-config`:

```toml
region = "central"
```

The region stays in that file, not in the command line or on the dashboard,
which only says "outdoor". With the file present, `run` and `record` poll
every 10 minutes for the hourly readings, and fill in up to a week after a
gap; `python3 -m aeromancer nea` polls only NEA. All five regions are stored,
as `nea_pm25_<region>`, each at the middle of the hour it averages; the
dashboard charts yours. See
[docs/outdoor-pm25.md](docs/outdoor-pm25.md) for why this source.

### Outdoor weather

Add home's position to the same file, and the recorder also stores what
NEA's nearest weather stations measure:

```toml
latitude = 1.35   # two decimals (about 1 km) are plenty
longitude = 103.85
```

Every 5 minutes it stores, from each of the 3 stations nearest to home, the
air temperature (`nea_temperature_<station>`, °C), relative humidity
(`nea_humidity_<station>`, %), rainfall (`nea_rain_<station>`, mm per
5 minutes), and wind speed and direction (`nea_wind_speed_<station>`, m/s;
`nea_wind_direction_<station>`, degrees it blows from), plus each station's
name and position in the `stations` table. After a gap it fills in up to a
day back, which takes several minutes, since data.gov.sg rate-limits
requests. The dashboard charts the nearest station's temperature and
humidity next to the indoor ones. Like the region, the position stays in
the file.

## Where the devices are

Readings only mean something together with where the device was. Record
each move when it happens (or with `--at` after the fact), as a room and a
free-text spot precise enough to recreate it:

```sh
python3 -m aeromancer place zytemp "living room" table --at start   # since before recording began
python3 -m aeromancer place blueair bedroom --at start
python3 -m aeromancer place zytemp bedroom "floor, 10 cm from the purifier's right-side intake"
python3 -m aeromancer place zytemp bedroom "..." --at "2026-10-17 21:30"   # local time; or just 21:30 for today
python3 -m aeromancer placements    # the history, with ids
python3 -m aeromancer unplace 3     # remove a mistaken record
```

Devices are `zytemp` (the meter's quantities) and `blueair` (`blueair_*`).
A placement holds until the next one of the same device. They are stored
in the `placements` table of the same database, and the dashboard marks
each move on the charts.

## The dashboard

Live CO₂ with a status (fresh < 800 ≤ stuffy < 1200 ≤ ventilate < 2000 ≤
leave the room), temperature, humidity on meters that have it, and two charts
of stacked panels on one time axis, one unit per panel: Air (CO₂ from the
meter and the purifier, particles with NEA's outdoor PM2.5 shaded behind
them, VOC, the purifier's pollution index) and
Climate (both temperatures, humidity). The meter is drawn in blue with
per-bucket min–max bands, the purifier in orange, NEA in green. Mercury retrograde periods
and full/new moons are marked on the time axis. Hover or use the arrow keys
on a chart to read every value at that moment.

## The Oracle

Each finding is computed honestly from your data and interpreted dishonestly.

| Finding | What is actually computed |
|---|---|
| Aura | mean CO₂, binned into colors |
| Lunar influence | Pearson correlation of CO₂ with lunar illumination |
| Mercury | share of ≥ 1000 ppm readings taken while Mercury was retrograde (real ephemeris), and its pre- and post-retrograde shadow |
| Chakra residency | time spent in each CO₂ band |
| Natal chart | the Sun's real zodiac sign; mean ppm read as ecliptic degrees |
| Schumann alignment | dominant period from a DFT, in octaves and cents below 7.83 Hz |
| Divine proportion | ratio of time CO₂ spends rising vs falling, compared with φ |
| Life path number | digital root of the mean ppm |
| Voices in the wire | for each undocumented code the meter sends (stored as `op_XX`), its correlation with CO₂, temperature, elapsed time and (over ≥ 7 days) the Moon; the strongest one picks its spirit |
| I Ching | the hexagram of the hour: each line is whether one source rose over the hour before (CO₂, temperature, the purifier's PM2.5, outdoor PM2.5, wind speed; the Moon by waxing), changing if it moved over twice its usual hourly change; a silent source's line is cast by three coins |
| Sensor society | correlation of every pair of series on one grid, with the Sun's height (over ≥ 1 day) and the Moon (over ≥ 7); the lag of the closest pair; who shares a room, from the placements |
| Household choir | each series' spectral centroid, all raised by the same number of octaves into a choir's range; the key by the Krumhansl–Schmuckler method; the intervals between voices. *Listen* plays it over the Schumann resonance |
| Souls present | occupants from the CO₂ balance V dC/dt = N·g − Q (C − 425 ppm): Q by regressing dC/dt on C, g = 18 L/h a person, V by the room's name |
| Birth certificates | each source's first reading: its Sun sign, Chinese year (from the new moon that began it) and biorhythms |
| Celestial clock | each series' daily peak, by least squares, in true solar time, as a planet on a horoscope wheel with houses and aspects; the planetary hours from real sunrise and sunset |
| Five elements | NEA's five regions as the five phases (east Wood, south Fire, central Earth, west Metal, north Water): their shares of PM2.5, and which region's PM2.5 moves first |
| Winds | a wind rose of the nearest station on the eight trigrams, the outdoor PM2.5 each wind brought, and the rain |
| Ward | the purifier's PM2.5 against outdoor PM2.5 over the same hours, and how late it follows |
| Horoscope | the last hour's trend and the above, assembled into advice, which never sends you out into the haze |

The dashboard groups the findings by what they read (today, the household,
the heavens, the island, numbers), and lists the main omens under its
header. `oracle` reads the same `nea.toml` as the recorder for the outdoor
findings; without it, or without the purifier, their cards just don't
appear. Planet positions use JPL's approximate Keplerian elements
(Standish), and Mercury's stations land within a day of the published
dates. The Moon uses the mean synodic month. None of it means anything.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
