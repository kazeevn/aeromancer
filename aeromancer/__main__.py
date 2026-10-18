"""Command line: ``python -m aeromancer {run,record,blueair,nea,pressure,health,health-login,serve,host,token,place,placements,unplace,oracle,kabbalah,prophecy,simulate}``."""

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

from . import blueair, filter_health, health, nea, oracle, pressure, push, server, tokens, weather
from .device import Reading
from .recorder import record, start_in_background
from .store import DEVICES, Placement, Store, default_path


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


def filter_settings(args) -> filter_health.Settings | None:
    """The room and purifier figures that turn a decay test into the filter's health, if configured."""
    try:
        return filter_health.load_settings(args.blueair_config)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        logging.error("%s; not judging the filter", e)
        return None


def start_health(args) -> None:
    """Poll Google Health alongside the meter if an OAuth client is configured."""
    try:
        client = health.load_client(args.health_client)
        if client is None:
            return
    except (ValueError, OSError) as e:
        logging.error("%s; not polling Google Health", e)
        return
    if not args.health_token.exists():
        logging.error("no Google Health login in %s; run health-login, until then not polling it", args.health_token)
        return
    health.start_in_background(args.db, client, args.health_token)


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


def meter_altitude(args) -> float | None:
    """The meter's altitude from its config file, or None (logged when it is bad)."""
    try:
        return pressure.load_altitude(args.zytemp_config)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        logging.error("%s; outdoor pressure at sea level only", e)
        return None


def start_outdoor(args) -> tuple[str | None, tuple[float, float] | None]:
    """Poll NEA's outdoor PM2.5 and weather, and the airports' pressure, for what is configured; return the region and home's position."""
    region, home = home_region(args), home_position(args)
    if region is not None:
        nea.start_in_background(args.db)
    if home is not None:
        weather.start_in_background(args.db, home)
        pressure.start_in_background(args.db, home, meter_altitude(args))
    return region, home


def remote(args) -> push.Remote | None:
    """The hosted dashboard this machine uploads to, or None when there is none (exits when its config is bad)."""
    try:
        return push.load_remote(args.remote_config)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        sys.exit(str(e))


def start_push(args) -> None:
    if (to := remote(args)) is not None:
        push.start_in_background(args.db, to)


def cmd_run(args):
    start_blueair(args)
    start_health(args)
    start_push(args)
    region, home = start_outdoor(args)
    status, _ = start_in_background(args.db, device=args.device, min_interval=args.min_interval)
    server.serve(
        args.db, args.host, args.port, recorder=status, outdoor_region=region, home=home, filter_settings=filter_settings(args)
    )


def cmd_record(args):
    start_blueair(args)
    start_health(args)
    start_push(args)
    start_outdoor(args)
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


def cmd_pressure(args):
    try:
        home, altitude = weather.load_home(args.nea_config), pressure.load_altitude(args.zytemp_config)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        sys.exit(str(e))
    if home is None:
        sys.exit(f"put the home position in {args.nea_config} (see docs/nea.md)")
    pressure.poll(args.db, home, altitude)


def _health_client_or_exit(args) -> dict:
    try:
        client = health.load_client(args.health_client)
    except ValueError as e:
        sys.exit(str(e))
    if client is None:
        sys.exit(f"download the Google Health OAuth client to {args.health_client} (see docs/health.md)")
    return client


def cmd_health(args):
    health.poll(args.db, _health_client_or_exit(args), args.health_token)


def cmd_health_login(args):
    health.login(_health_client_or_exit(args), args.health_token, open_browser=not args.no_browser)


def cmd_serve(args):
    server.serve(
        args.db,
        args.host,
        args.port,
        outdoor_region=home_region(args),
        home=home_position(args),
        filter_settings=filter_settings(args),
    )


def cmd_host(args):
    Store(args.db).close()  # create the database and its tables before the first request
    start_blueair(args)
    start_health(args)
    region, home = start_outdoor(args)
    server.serve(
        args.db, args.host, args.port, outdoor_region=region, home=home, filter_settings=filter_settings(args), auth=True
    )


def default_host_config() -> Path:
    return nea.default_config_path().with_name("host.toml")


def share_url(args, secret: str) -> str:
    """The address that lets the token's holder in: the hosted dashboard's (host.toml), or just the token."""
    try:
        with args.host_config.open("rb") as f:
            url = tomllib.load(f).get("url")
    except FileNotFoundError:
        url = None
    return f"{url.rstrip('/')}/?t={secret}" if url else secret


def parse_lifetime(text: str) -> float | None:
    """'7d', '12h' -> seconds; 'never' -> None."""
    if text == "never":
        return None
    try:
        seconds = server.parse_range(text)
    except ValueError:
        seconds = None
    if seconds is None or seconds <= 0:
        raise argparse.ArgumentTypeError(f"not a lifetime like 7d, 12h or never: {text!r}")
    return seconds


def cmd_token_add(args):
    store = Store(args.db)
    secret = tokens.issue(store, args.name, "write" if args.write else "view", args.lifetime)
    print(secret if args.write else share_url(args, secret))


def cmd_token_list(args):
    now = time.time()
    rows = tokens.list_tokens(Store(args.db, readonly=True))
    if not rows:
        print("no tokens")
    for t in rows:
        if t.revoked is not None:
            state = "revoked " + describe_when(t.revoked)
        elif t.expires is None:
            state = "never expires"
        else:
            state = ("expired " if t.expires <= now else "expires ") + describe_when(t.expires)
        print(f"{t.id:>4}  {t.scope:<5}  {t.name:<20}  {state}")


def cmd_token_revoke(args):
    if not tokens.revoke(Store(args.db), args.id):
        sys.exit(f"no unrevoked token {args.id}")


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


def _call_or_exit(to: push.Remote, method: str, path: str, body=None):
    try:
        return push.call(to, method, path, body)
    except (OSError, RuntimeError, ValueError) as e:
        sys.exit(str(e))


def cmd_place(args):
    if args.at > time.time() + 60:
        sys.exit("that is in the future; record the move when it happens")
    if (to := remote(args)) is not None:
        _call_or_exit(to, "POST", "/api/placements", {"ts": args.at, "device": args.device, "room": args.room, "spot": args.spot})
    else:
        Store(args.db).place(args.at, args.device, args.room, args.spot)
    cmd_placements(args)


def cmd_placements(args):
    if (to := remote(args)) is not None:
        query = f"?device={args.device}" if args.device else ""
        placements = [Placement(**p) for p in _call_or_exit(to, "GET", "/api/placements" + query)]
    else:
        placements = Store(args.db, readonly=True).placements(args.device)
    if not placements:
        print("no placements recorded")
    for p in placements:
        print(f"{p.id:>4}  {describe_when(p.ts):<16}  {p.device:<7}  {p.room}" + (f": {p.spot}" if p.spot else ""))


def cmd_unplace(args):
    if (to := remote(args)) is not None:
        _call_or_exit(to, "DELETE", f"/api/placements/{args.id}")
    elif not Store(args.db).unplace(args.id):
        sys.exit(f"no placement {args.id}")


def print_findings(result):
    for f in result["findings"]:
        print(f"\n\033[1m{f['title']}: {f['headline']}\033[0m")
        for line in reversed(f["lines"] if f["id"] == "iching" else []):  # drawn from the top, cast from the bottom
            mark = ("\u25cb" if line["yang"] else "\u00d7") if line["changing"] else " "
            print(f"  {'\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501' if line['yang'] else '\u2501\u2501\u2501\u2501 \u2501\u2501\u2501\u2501'} {mark}  {line['caster']}: {line['why']}")
        print(textwrap.fill(f["body"], 78, initial_indent="  ", subsequent_indent="  "))
        for s in f.get("signals", []):
            print(f"  \033[1m{s['op']}\033[0m {s['persona']}, {s['min']:g}\u2013{s['max']:g}")
            print(textwrap.fill(s["reading"], 78, initial_indent="       ", subsequent_indent="       "))
        for c in f.get("coincidences", []):
            print(textwrap.fill(c["text"], 78, initial_indent="  • ", subsequent_indent="    "))
        print_prophecy(f.get("prophecy") or {})
        print(f"  \033[2mCertainty: {f['certainty']}\033[0m")
    print(f"\n\033[2m{result['disclaimer']}\033[0m")


PROPHECY_LINES = (("foretold", "Foretold"), ("counsel", "Counsel"), ("revealed", "Revealed"))


def print_prophecy(prophecy: dict, indent: str = "  "):
    italic, plain = "\033[3m", "\033[0m"
    for key, label in PROPHECY_LINES:
        if prophecy.get(key):
            # The escape codes take characters but no room on the screen.
            print(textwrap.fill(f"{italic}{label}:{plain} {prophecy[key]}", 78 + len(italic + plain), initial_indent=indent, subsequent_indent=indent + "  "))


def cmd_oracle(args):
    print_findings(server.run_oracle(Store(args.db, readonly=True), args.range, home_region(args), home_position(args)))


def cmd_prophecy(args):
    result = server.run_prophecy(Store(args.db, readonly=True), args.range, home_region(args), home_position(args))
    if result["councils"]:
        print(f"\n\033[1m{result['title']}: {result['headline']}\033[0m")
        if result["spread"]:
            print("  " + " · ".join(f"{c['position']}: {c['numeral']} {c['name']}" for c in result["spread"]))
        print_prophecy(result["prophecy"])
        print(f"  \033[2mCertainty: {result['certainty']}\033[0m")
    for c in result["councils"]:
        skeptic = c["skeptic"]["error"]
        print(f"\n\033[1mThe council on {c['name']}\033[0m, {c['unit']}, for the next {oracle._duration(c['horizon'])}")
        print(f"  {'seer':<28} {'foresees':>9} {'error':>7} {'skill':>7} {'weight':>7}")
        for s in c["seers"]:
            foresees = f"{s['forecast'][-1][1]:.0f}" if s["forecast"] else "–"
            error = f"{s['error']:.0f}" if s["error"] is not None else "untried"
            skill = f"{s['skill']:+.0%}" if s["skill"] is not None else ""
            print(f"  {s['name']:<28} {foresees:>9} {error:>7} {skill:>7} {s['weight']:>7.0%}")
        council_error = f"{c['error']:.0f}" if c["error"] is not None else "–"
        print(f"  {'The council':<28} {c['forecast'][-1][1]:>9.0f} {council_error:>7}")
        if skeptic is not None:
            print(f"  {'The Skeptic (no change)':<28} {c['skeptic']['value']:>9.0f} {skeptic:>7.0f}")
    print(f"\n\033[2m{result['disclaimer']}\033[0m")


def cmd_kabbalah(args):
    print_findings(server.run_kabbalah(Store(args.db, readonly=True), args.range, home_region(args), home_position(args)))


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
        meter(p)
        wearable(p)
        uploading(p)

    def uploading(p):
        p.add_argument(
            "--remote-config",
            type=Path,
            default=push.default_config_path(),
            help="the hosted dashboard to upload to and place devices on (default: %(default)s)",
        )

    def purifier(p):
        p.add_argument(
            "--blueair-config", type=Path, default=blueair.default_config_path(), help="Blueair login and filter settings (default: %(default)s)"
        )

    def outdoor(p):
        p.add_argument(
            "--nea-config", type=Path, default=nea.default_config_path(), help="NEA home region and position (default: %(default)s)"
        )

    def meter(p):
        p.add_argument(
            "--zytemp-config", type=Path, default=pressure.default_altitude_path(), help="the meter's altitude (default: %(default)s)"
        )

    def wearable(p):
        p.add_argument(
            "--health-client",
            type=Path,
            default=health.default_client_path(),
            help="Google Health OAuth client (default: %(default)s)",
        )
        p.add_argument(
            "--health-token", type=Path, default=health.default_token_path(), help="its refresh token (default: %(default)s)"
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

    p = sub.add_parser("pressure", help="poll the air pressure the airports around Singapore report only")
    outdoor(p)
    meter(p)
    p.set_defaults(func=cmd_pressure)

    p = sub.add_parser("health", help="poll Google Health (a Fitbit or Pixel Watch) only")
    wearable(p)
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("health-login", help="allow aeromancer to read Google Health, and save the login")
    wearable(p)
    p.add_argument("--no-browser", action="store_true", help="only print the address to open")
    p.set_defaults(func=cmd_health_login)

    p = sub.add_parser("serve", help="serve the dashboard only")
    serving(p)
    purifier(p)
    outdoor(p)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("host", help="poll the online sources and serve the dashboard to token holders (docs/cloud.md)")
    purifier(p)
    outdoor(p)
    meter(p)
    wearable(p)
    p.add_argument("--host", default="127.0.0.1", help="behind a TLS proxy such as Caddy (default: %(default)s)")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_host)

    p = sub.add_parser("token", help="let people see the hosted dashboard, and machines upload to it")
    tokens_sub = p.add_subparsers(required=True)
    t = tokens_sub.add_parser("add", help="issue a token, and print the link that uses it")
    t.add_argument("name", help="whom it is for, e.g. alice or laptop")
    t.add_argument("--write", action="store_true", help="for a recording machine: upload, but not view")
    t.add_argument(
        "--for", dest="lifetime", type=parse_lifetime, default=7 * 86400, help="e.g. 12h, 30d or never (default: 7d)"
    )
    t.add_argument(
        "--host-config", type=Path, default=default_host_config(), help="the dashboard's address (default: %(default)s)"
    )
    t.set_defaults(func=cmd_token_add)
    t = tokens_sub.add_parser("list", help="list the tokens")
    t.set_defaults(func=cmd_token_list)
    t = tokens_sub.add_parser("revoke", help="stop a token working, at once")
    t.add_argument("id", type=int, help="as listed by token list")
    t.set_defaults(func=cmd_token_revoke)

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
    uploading(p)
    p.set_defaults(func=cmd_place)

    p = sub.add_parser("placements", help="list where the devices have been")
    p.add_argument("device", nargs="?", choices=DEVICES)
    uploading(p)
    p.set_defaults(func=cmd_placements)

    p = sub.add_parser("unplace", help="remove a mistaken placement record")
    p.add_argument("id", type=int, help="as listed by placements")
    uploading(p)
    p.set_defaults(func=cmd_unplace)

    p = sub.add_parser("oracle", help="print the pseudo-scientific analysis")
    p.add_argument("--range", default="24h", help="e.g. 90m, 24h, 7d, all")
    outdoor(p)
    p.set_defaults(func=cmd_oracle)

    p = sub.add_parser("kabbalah", help="print the pseudo-mystical analysis")
    p.add_argument("--range", default="24h", help="e.g. 90m, 24h, 7d, all")
    outdoor(p)
    p.set_defaults(func=cmd_kabbalah)

    p = sub.add_parser("prophecy", help="print the council of seers and their unified prophecy")
    p.add_argument("--range", default="24h", help="e.g. 90m, 24h, 7d, all")
    outdoor(p)
    p.set_defaults(func=cmd_prophecy)

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
