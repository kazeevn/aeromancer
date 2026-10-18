# Outdoor PM2.5 and weather (Singapore)

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
dashboard charts yours.

## Outdoor weather

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

## Why NEA via data.gov.sg

The Blueair app shows outdoor air quality, but that comes from BreezoMeter (now Google), and
`blueair_api` doesn't expose it. We use NEA's own measurements instead, from
`https://api-open.data.gov.sg/v2/real-time/api/pm25` (see `aeromancer/nea.py`).

- **Measured, not modelled.** It is the 1-hour mean PM2.5 from NEA's monitoring network, for five
  regions (north, south, east, west, central), published hourly and stamped with the hour's end.
- **Free, and needs no key.** `?date=YYYY-MM-DD` returns a whole day, which is how gaps are
  filled.
- **Rate limits.** Bursts of requests get `429 Too Many Requests`. On 2026-10-17 a runaway test
  loop caused this for dated queries, while the latest-reading call kept working. Backfill
  therefore waits 5 s between days and stores each day as it arrives. Adding a data.gov.sg API key
  should raise the limit if this ever matters.
- **More pollutants.** The `psi` endpoint adds PM10, O3, CO, SO2 and NO2 sub-indices by region, if
  we ever want them.

## Which hour a reading covers

[NEA's FAQ](https://www.nea.gov.sg/our-services/pollution-control/air-pollution/faqs) says only that the 1-hr PM2.5 "reflect[s] the average concentration of fine particulate
matter (PM2.5) over one hour". [data.gov.sg](https://guide.data.gov.sg/developer-guide/real-time-apis) describes `timestamp` as the "SGT timestamp of the
reading". Neither says which hour. The publication times answer it:

- The reading stamped `2026-10-17T20:00:00+08:00` was served at 20:12 with
  `updatedTimestamp` 20:00:35 and its final values. Fetched again at 20:38, `updatedTimestamp`
  had moved to 20:30:51, but every value was the same.
- A value published 35 s after 20:00 can't contain air measured after 20:00. So the reading
  stamped *T* is the mean over *T* − 1 h to *T*, the hour ending at its timestamp. This is the
  common convention, e.g. [Florida's air monitoring reports](https://prodapps.dep.state.fl.us/flaqs/AirQualityMonitoring/Reports/Daily/120992005/15-01-2026/*)
  state "data are time-stamped at the end of the hour".
- Older readings show `updatedTimestamp` about 45 min after `timestamp` (2732–2749 s for
  2026-10-16), which looks like a later re-save, not a different window.

We therefore store each reading at *T* − 30 min, the middle of the hour it averages, so that it
lines up with the 5-minute indoor readings. Rows stored by the first version at *T* are moved
when the poller starts (`restamp_hour_ends`).

Not ruled out: that NEA's "hour" is an average lagged by more than its stamp suggests. Comparing
outdoor and indoor PM2.5 while windows are open could test this, since indoor should follow
outdoor within minutes.

## Alternatives considered

- **Open-Meteo air quality** (free, no key): it is modelled. At 2026-10-17 20:00 it read 41 µg/m³
  for Singapore, while NEA measured 79–187 µg/m³ across the regions during the haze.
- **Google Air Quality API** (the BreezoMeter data the Blueair app shows): it needs a Cloud
  project with billing, and it is also a model.
- **Low-cost sensor networks** (PurpleAir, sensor.community): no open Singapore network was found.

## Choosing the region

NEA defines its regions as lists of towns, not as boundaries. Pick the region listing your town,
or the nearest one. All five are stored, so the choice can be revisited by checking which region
best tracks the purifier's PM2.5 when windows are open. The home region lives in the private
`~/.config/aeromancer/nea.toml`, not in the repository.
