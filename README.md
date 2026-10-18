# Aeromancer

Records the ZyAura / Holtek "USB-zyTemp" CO₂ meter (USB `04d9:a052`), stores
the readings in SQLite, draws them on a local dashboard, and runs a
strictly pseudo-scientific analysis of your air. Optionally it also records
a Blueair purifier and Singapore's outdoor PM2.5 and weather.

Pure Python standard library (3.11+): no packages to install, unless you
also want the optional Blueair purifier poller.

## Quick start

Let your user read the meter (once):

```sh
sudo install -m644 udev/70-aeromancer.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=hidraw
```

Then record and open the dashboard at http://127.0.0.1:8000:

```sh
python3 -m aeromancer run
```

To try the dashboard without the meter:

```sh
python3 -m aeromancer --db /tmp/demo.sqlite3 simulate --days 14
python3 -m aeromancer --db /tmp/demo.sqlite3 serve
```

## Documentation

- [Recording](docs/recording.md): commands, the database, running as a
  service, and where the devices are
- [Blueair purifier](docs/blueair.md): the optional purifier poller
- [Outdoor PM2.5 and weather](docs/nea.md): the optional NEA poller
  (Singapore), and why this source
- [The dashboard](docs/dashboard.md)
- [The Oracle](docs/oracle.md) and [the Tree of Life](docs/kabbalah.md): the
  analyses, and what each one actually computes
- [Ideas](docs/ideas/ideas.md) not tried yet, and [past studies](docs/archive/)

## Tests

```sh
python3 -m unittest discover -s tests -t .
```
