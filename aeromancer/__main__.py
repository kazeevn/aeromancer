"""Command line: ``python -m aeromancer {run,record,blueair,nea,serve,place,placements,unplace,oracle,simulate}``."""

from __future__ import annotations

import argparse
import datetime
import logging
import math
import random
import sys
import textwrap
import time
import tomllib
from pathlib import Path

from . import blueair, nea, server, weather
from .device import Reading
from .recorder import record, start_in_background
from .store import DEVICES, Store, default_path


def start_blueair(args) -> None:
    """Poll the purifier alongside the meter if a Blueair login is configured."""
    try:
        config = blueair.load_config(args.blueair_config)
        if config is None:
            return
        blueair.check_installed()
    except (blueair.Unavailable, ValueError, tomllib.TOMLDecodeError) as e:
        logging.error("%s; not polling the purifier", e)
        return
    blueair.start_in_background(args.db, config)


def home_region(args) -> str | None:
    """The NEA region from the config file, or None (logged) when there is none or it is bad."""
    try:
        return nea.load_region(args.nea_config)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        logging.error("%s; no outdoor PM2.5", e)
        return None


def home_position(args) -> tuple[float, float] | None:
    """Home's latitude and longitude from the config file, or None (logged) when there are none or they are bad."""
    try:
        return weather.load_home(args.nea_config)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        logging.error("%s; no outdoor weather", e)
        return None


def start_nea(args) -> tuple[str | None, tuple[float, float] | None]:
    """Poll NEA's outdoor PM2.5 and weather for what is configured; return the region and home's position."""
    region, home = home_region(args), home_position(args)
    if region is not None:
        nea.start_in_background(args.db)
    if home is not None:
        weather.start_in_background(args.db, home)
    return region, home


def cmd_run(args):
    start_blueair(args)
    region, home = start_nea(args)
    status, _ = start_in_background(args.db, device=args.device, min_interval=args.min_interval)
    server.serve(args.db, args.host, args.port, recorder=status, outdoor_region=region, home=home)


def cmd_record(args):
    start_blueair(args)
    start_nea(args)
    record(args.db, device=args.device, min_interval=args.min_interval)


def cmd_blueair(args):
    try:
        config = blueair.load_config(args.blueair_config)
        if config is None:
            sys.exit(f"put the Blueair app login in {args.blueair_config} (see README)")
        blueair.check_installed()
    except (blueair.Unavailable, ValueError, tomllib.TOMLDecodeError) as e:
        sys.exit(str(e))
    blueair.poll(args.db, config)


def cmd_nea(args):
    try:
        region, home = nea.load_region(args.nea_config), weather.load_home(args.nea_config)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        sys.exit(str(e))
    if region is None and home is None:
        sys.exit(f"put the home region or position in {args.nea_config} (see README)")
    if region is None:
        return weather.poll(args.db, home)
    if home is not None:
        weather.start_in_background(args.db, home)
    nea.poll(args.db)


def cmd_serve(args):
    server.serve(args.db, args.host, args.port, outdoor_region=home_region(args), home=home_position(args))


def parse_when(text: str) -> float:
    """'start' -> 0 (since before recording began); local 'YYYY-MM-DD HH:MM' or 'HH:MM' (today) -> unix time."""
    if text == "start":
        return 0.0
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        try:
            clock = datetime.time.fromisoformat(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not 'start', a date and time or a time of day: {text!r}") from None
        when = datetime.datetime.combine(datetime.date.today(), clock)
    return when.timestamp()  # naive means local time


def describe_when(ts: float) -> str:
    return "since the start" if ts == 0 else datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def cmd_place(args):
    store = Store(args.db)
    if args.at > time.time() + 60:
        sys.exit("that is in the future; record the move when it happens")
    store.place(args.at, args.device, args.room, args.spot)
    cmd_placements(args)


def cmd_placements(args):
    store = Store(args.db)
    placements = store.placements(args.device)
    if not placements:
        print("no placements recorded")
    for p in placements:
        print(f"{p.id:>4}  {describe_when(p.ts):<16}  {p.device:<7}  {p.room}" + (f": {p.spot}" if p.spot else ""))


def cmd_unplace(args):
    if not Store(args.db).unplace(args.id):
        sys.exit(f"no placement {args.id}")


def cmd_oracle(args):
    result = server.run_oracle(Store(args.db), args.range, home_region(args), home_position(args))
    for f in result["findings"]:
        print(f"\n\033[1m{f['title']}: {f['headline']}\033[0m")
        for line in reversed(f["lines"] if f["id"] == "iching" else []):  # drawn from the top, cast from the bottom
            mark = ("\u25cb" if line["yang"] else "\u00d7") if line["changing"] else " "
            print(f"  {'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501' if line['yang'] else '\u2501\u2501\u2501\u2501 \u2501\u2501\u2501\u2501'} {mark}  {line['caster']}: {line['why']}")
        print(textwrap.fill(f["body"], 78, initial_indent="  ", subsequent_indent="  "))
        for s in f.get("signals", []):
            print(f"  \033[1m{s['op']}\033[0m {s['persona']}, {s['min']:g}\u2013{s['max']:g}")
            print(textwrap.fill(s["reading"], 78, initial_indent="       ", subsequent_indent="       "))
        print(f"  \033[2mCertainty: {f['certainty']}\033[0m")
    print(f"\n\033[2m{result['disclaimer']}\033[0m")


def cmd_simulate(args):
    """Synthetic office air: people arrive, breathe, open windows, go home."""
    rng = random.Random(args.seed)
    end = time.time()
    t = end - args.days * 86400
    co2, temp = 430.0, 20.5
    window_until = 0.0
    readings = []
    while t < end:
        now = time.localtime(t)
        occupied = now.tm_wday < 5 and 8.5 <= now.tm_hour + now.tm_min / 60 <= 18.5
        people = 2 + rng.random() if occupied else 0
        if occupied and rng.random() < 0.003:
            window_until = t + rng.uniform(300, 1200)
        leak = 0.03 if t < window_until else 0.004
        co2 += people * 1.6 - (co2 - 420) * leak + rng.gauss(0, 2)
        temp += ((23.0 if occupied else 20.0) - (2.0 if t < window_until else 0) - temp) * 0.01
        readings.append(Reading(t, "co2", round(max(400, co2))))
        readings.append(Reading(t + 1, "temperature", round(temp + rng.gauss(0, 0.03), 2)))
        # Stand-ins for the undocumented codes, shaped like the real meter's.
        readings.append(Reading(t + 2, "op_71", round(max(400, co2)) - 60))
        readings.append(Reading(t + 2, "op_6d", 3247))
        readings.append(Reading(t + 2, "op_6e", 27160 + rng.randint(-8, 8)))
        readings.append(Reading(t + 2, "op_43", 3608 + round((temp - 21) * 4)))
        t += 30
    store = Store(args.db)
    store.add(readings)
    print(f"wrote {len(readings)} synthetic readings to {args.db}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="aeromancer", description=__doc__)
    parser.add_argument("--db", type=Path, default=default_path(), help="SQLite file (default: %(default)s)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(required=True)

    def recording(p):
        p.add_argument("--device", help="hidraw node (default: autodetect 04d9:a052)")
        p.add_argument("--min-interval", type=float, default=5.0, help="seconds between stored readings")
        purifier(p)
        outdoor(p)

    def purifier(p):
        p.add_argument(
            "--blueair-config", type=Path, default=blueair.default_config_path(), help="Blueair login (default: %(default)s)"
        )

    def outdoor(p):
        p.add_argument(
            "--nea-config", type=Path, default=nea.default_config_path(), help="NEA home region and position (default: %(default)s)"
        )

    def serving(p):
        where = p.add_mutually_exclusive_group()
        where.add_argument("--host", default="127.0.0.1")
        where.add_argument(
            "--public", dest="host", action="store_const", const="0.0.0.0", help="serve on all interfaces (no auth!)"
        )
        p.add_argument("--port", type=int, default=8000)

    p = sub.add_parser("run", help="record and serve the dashboard")
    recording(p)
    serving(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("record", help="record only")
    recording(p)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("blueair", help="poll the Blueair purifier only")
    purifier(p)
    p.set_defaults(func=cmd_blueair)

    p = sub.add_parser("nea", help="poll NEA's outdoor PM2.5 and weather (Singapore) only")
    outdoor(p)
    p.set_defaults(func=cmd_nea)

    p = sub.add_parser("serve", help="serve the dashboard only")
    serving(p)
    outdoor(p)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser(
        "place",
        help="record where a device is",
        description="Record that a device is somewhere from now (or --at) on. To correct a mistake, "
        "remove it with unplace and record it again.",
    )
    p.add_argument("device", choices=DEVICES)
    p.add_argument("room", help="e.g. bedroom")
    p.add_argument("spot", nargs="?", default="", help="where in the room, e.g. 'floor, 10 cm from the intake'")
    p.add_argument(
        "--at",
        type=parse_when,
        default=time.time(),
        help="when it got there: 'YYYY-MM-DD HH:MM' or 'HH:MM' local time, or 'start' for since before recording began "
        "(default: now)",
    )
    p.set_defaults(func=cmd_place)

    p = sub.add_parser("placements", help="list where the devices have been")
    p.add_argument("device", nargs="?", choices=DEVICES)
    p.set_defaults(func=cmd_placements)

    p = sub.add_parser("unplace", help="remove a mistaken placement record")
    p.add_argument("id", type=int, help="as listed by placements")
    p.set_defaults(func=cmd_unplace)

    p = sub.add_parser("oracle", help="print the pseudo-scientific analysis")
    p.add_argument("--range", default="24h", help="e.g. 90m, 24h, 7d, all")
    outdoor(p)
    p.set_defaults(func=cmd_oracle)

    p = sub.add_parser("simulate", help="fill a database with synthetic data")
    p.add_argument("--days", type=float, default=7)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_simulate)

    args = parser.parse_args(argv)
    if args.func is cmd_simulate and "--db" not in (argv or sys.argv):
        parser.error("simulate needs an explicit --db so it never pollutes real recordings")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        args.func(args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
