# co2monitor

Records the ZyAura / Holtek "USB-zyTemp" CO₂ meter (USB `04d9:a052`), stores
the readings in SQLite, draws them on a local dashboard, and runs a
strictly pseudo-scientific analysis of your air.

Pure Python standard library (3.11+): no packages to install.

## Setup

Let your user read the meter (once):

```sh
sudo install -m644 udev/70-co2monitor.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw
```

## Usage

```sh
python3 -m co2monitor run            # record + dashboard at http://127.0.0.1:8000
python3 -m co2monitor record         # record only
python3 -m co2monitor serve          # dashboard only (reads the same database)
python3 -m co2monitor oracle --range 7d   # the analysis, in the terminal
```

Readings go to `~/.local/share/co2monitor/readings.sqlite3` (override with
`--db`), at most one per quantity every 5 s (`--min-interval`). The recorder
survives the meter being unplugged and picks it up again.

To record all the time, as a systemd user service:

```sh
cp systemd/co2monitor.service ~/.config/systemd/user/
systemctl --user enable --now co2monitor
```

To try the dashboard without the meter:

```sh
python3 -m co2monitor --db /tmp/demo.sqlite3 simulate --days 14
python3 -m co2monitor --db /tmp/demo.sqlite3 serve
```

## The dashboard

Live CO₂ with a status (fresh < 800 ≤ stuffy < 1200 ≤ ventilate < 2000 ≤
leave the room), temperature, humidity on meters that have it, CO₂ and
temperature charts with per-bucket min–max bands, a data table, and Mercury
retrograde periods and full/new moons marked on the time axis. Hover or use
the arrow keys on a chart to read values.

## The Oracle

Each finding is computed honestly from your data and interpreted dishonestly.

| Finding | What is actually computed |
|---|---|
| Aura | mean CO₂, binned into colors |
| Lunar influence | Pearson correlation of CO₂ with lunar illumination |
| Mercury | share of ≥ 1000 ppm readings taken while Mercury was retrograde (real ephemeris) |
| Chakra residency | time spent in each CO₂ band |
| Natal chart | the Sun's real zodiac sign; mean ppm read as ecliptic degrees |
| Schumann alignment | dominant period from a DFT, in octaves and cents below 7.83 Hz |
| Divine proportion | ratio of time CO₂ spends rising vs falling, compared with φ |
| Life path number | digital root of the mean ppm |
| Voices in the wire | for each undocumented code the meter sends (stored as `op_XX`), its correlation with CO₂, temperature, elapsed time and (over ≥ 7 days) the Moon; the strongest one picks its spirit |
| Horoscope | the last hour's trend and the above, assembled into advice |

Planet positions use JPL's approximate Keplerian elements (Standish), and
Mercury's stations land within a day of the published dates. The Moon uses
the mean synodic month. None of it means anything.

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
