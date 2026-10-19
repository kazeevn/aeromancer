# Recording

## Commands

```sh
python3 -m aeromancer run            # record + dashboard at http://127.0.0.1:8000
python3 -m aeromancer record         # record only
python3 -m aeromancer serve          # dashboard only (reads the same database)
python3 -m aeromancer oracle --range 7d   # the analysis, in the terminal
python3 -m aeromancer kabbalah --range 7d # the Tree of Life, in the terminal
python3 -m aeromancer prophecy --range 7d # the council of seers and its prophecy
```

`run` and `serve` listen on localhost only; add `--public` to serve the
dashboard on all interfaces, e.g. to read it from your phone. It has no
login, so anyone on the network can see it.

Readings go to `~/.local/share/aeromancer/readings.sqlite3` (override with
`--db`), at most one per quantity every 5 s (`--min-interval`). The recorder
survives the meter being unplugged and picks it up again.

The purifier ([blueair.md](blueair.md)), outdoor ([nea.md](nea.md),
[pressure.md](pressure.md)) and wearable ([health.md](health.md)) pollers
start with `run` and `record` when their config files exist, and so does the
upload to a hosted dashboard ([cloud.md](cloud.md)).

## As a service

To record all the time, as a systemd user service:

```sh
cp systemd/aeromancer.service ~/.config/systemd/user/
systemctl --user enable --now aeromancer
```

## Where the devices are

Readings only mean something together with where the device was. Record
each move when it happens (or with `--at` after the fact), as a room and a
free-text spot precise enough to recreate it:

```sh
python3 -m aeromancer place zytemp "living room" table --at start   # since before recording began
python3 -m aeromancer place blueair bedroom --at start
python3 -m aeromancer place zytemp bedroom "floor, 10 cm from the purifier's right-side intake"
python3 -m aeromancer place zytemp bedroom "..." --at "2026-10-17 21:30"   # local time; or just 21:30 for today
python3 -m aeromancer place blueair "living room" "..." --outdoor-intake   # inside, but drawing outside air
python3 -m aeromancer placements    # the history, with ids
python3 -m aeromancer unplace 3     # remove a mistaken record
```

Devices are `zytemp` (the meter's quantities) and `blueair` (`blueair_*`).
A placement holds until the next one of the same device. They are stored
in the `placements` table of the same database, and the dashboard marks
each move on the charts.

`--outdoor-intake` is for a device that stands inside but draws mostly
outside air. Its readings of the air (not the purifier's settings and
counters) then describe the outside air, so the divinations, which read
the house's air, leave them out until the next placement without the flag.
The charts still show them, and the tooltip names them "outdoor intake".
A device standing outside altogether is not this: give the place it stands
as its room instead.

## What the meter sends

Besides `co2` and `temperature`, the meter sends codes that the recorder
stores raw, as `op_XX` with the code in hex. Most arrive every 5–10 s:
intermediate stages of the CO2 calculation and raw sensor samples. Some
arrive only in a dump of 52 items when the meter powers up. One of those,
`op_4d`, is the altitude setting in metres. The meter scales its CO2 by
about the air-pressure ratio for that altitude, so set it to your altitude.
The frames just after power-up can carry stale CO2 values.
[archive/zytemp-channels.md](archive/zytemp-channels.md) has what each code
is, and how we found out.
