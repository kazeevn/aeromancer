# Recording

## Commands

```sh
python3 -m aeromancer run            # record + dashboard at http://127.0.0.1:8000
python3 -m aeromancer record         # record only
python3 -m aeromancer serve          # dashboard only (reads the same database)
python3 -m aeromancer oracle --range 7d   # the analysis, in the terminal
python3 -m aeromancer kabbalah --range 7d # the Tree of Life, in the terminal
```

`run` and `serve` listen on localhost only; add `--public` to serve the
dashboard on all interfaces, e.g. to read it from your phone. It has no
login, so anyone on the network can see it.

Readings go to `~/.local/share/aeromancer/readings.sqlite3` (override with
`--db`), at most one per quantity every 5 s (`--min-interval`). The recorder
survives the meter being unplugged and picks it up again.

The purifier ([blueair.md](blueair.md)) and outdoor ([nea.md](nea.md))
pollers start with `run` and `record` when their config files exist.

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
python3 -m aeromancer placements    # the history, with ids
python3 -m aeromancer unplace 3     # remove a mistaken record
```

Devices are `zytemp` (the meter's quantities) and `blueair` (`blueair_*`).
A placement holds until the next one of the same device. They are stored
in the `placements` table of the same database, and the dashboard marks
each move on the charts.
