# Outdoor air pressure (Singapore)

The recorder also stores the air pressure that the airports around Singapore
report, and interpolates it for home: at sea level, and at the height of the
CO₂ meter. NEA's data.gov.sg API publishes no pressure, so this is the only
free, measured source we found. Both sources are free, need no key, and use
the standard library only.

It starts with `run` and `record` once `~/.config/aeromancer/nea.toml` gives
home's position (see [nea.md](nea.md)). `python3 -m aeromancer pressure`
polls only the pressure. For the pressure at the meter's height, give its
altitude above mean sea level in `~/.config/aeromancer/zytemp.toml`, or in
another file passed with `--zytemp-config`:

```toml
altitude_m = 30  # metres above mean sea level
```

Like home's position, the altitude stays in that file, out of the
repository. Without it, only the sea-level pressure is stored.

## What is stored

Every 30 minutes the poller fetches the new reports. After a gap it fills in
up to a week back, and it re-reads the last 3 hours for late reports.

| Quantity | What | Unit |
|---|---|---|
| `synop_msl_<WMO id>` | sea-level pressure from a SYNOP | hPa, 0.1 |
| `synop_pressure_<WMO id>` | pressure at the station's barometer | hPa, 0.1 |
| `synop_temperature_<WMO id>`, `synop_dewpoint_<WMO id>` | air temperature, dew point | °C, 0.1 |
| `metar_qnh_<ICAO id>` | QNH from a METAR | hPa, whole, rounded down |
| `metar_temperature_<ICAO id>`, `metar_dewpoint_<ICAO id>` | air temperature, dew point | °C, whole |
| `home_pressure_msl` | interpolated sea-level pressure at home, each hour | hPa |
| `home_pressure` | the same at the meter's altitude | hPa |

Raw reports are stored at their observation times (UTC hours, which are SGT
hours too), and the interpolated values on each hour. The airports' names,
positions and elevations, as aviationweather.gov lists them, go into the
`stations` table under their ICAO ids. A SYNOP station is taken to stand at
the airport whose METARs it shares.

| Airport | ICAO | WMO (SYNOP) | Reports |
|---|---|---|---|
| Changi | WSSS | 48698 | METAR every 30 min, SYNOP every 3 h |
| Paya Lebar | WSAP | | METAR hourly |
| Seletar | WSSL | | METAR hourly |
| Senai, Johor | WMKJ | 48679 | METAR and SYNOP hourly |
| Hang Nadim, Batam | WIDD | | METAR every 30 min |
| Tanjung Pinang, Bintan | WIDN | 96091 | METAR every 30 min, SYNOP hourly |

Ogimet had no SYNOPs from Paya Lebar (48694) or Seletar (48692, 48699) from
2026-10-10 to 18, nor from Batam (96087) on 2026-10-17 and 18.

## Sources

- **SYNOP**, through [Ogimet](https://www.ogimet.com/)
  (`https://www.ogimet.com/cgi-bin/getsynop?block=<WMO id>&begin=...&end=...`):
  the synoptic reports that weather stations send to the WMO. The pressures
  come in tenths of a hPa: group `3PPPP` is the pressure at the station, and
  `4PPPP` is the pressure reduced to sea level. The poller makes one request
  per station.
- **METAR**, through [aviationweather.gov](https://aviationweather.gov/data/api/)
  (`https://aviationweather.gov/api/data/metar?ids=...&hours=24&date=...&format=json`):
  the airports' routine reports for pilots. QNH (`Q1009`) is in whole hPa.
  ICAO rounds it down, not to the nearest: at Changi, 14 of 15 hours over
  2026-10-15 to 18 had the METAR equal the SYNOP's sea-level pressure rounded down.
  The API returns at most 400 reports per request, so it is asked one day at a
  time. SPECIs, the special reports between the hours, are skipped.

## Interpolation

For each hour, every station that reported within 10 minutes of it gives a
sea-level pressure:

- **SYNOP:** its sea-level pressure as reported, weighted as σ = 0.1 hPa.
- **METAR:** QNH is defined through the ICAO standard atmosphere, 15 °C at
  sea level. Singapore's air is about 30 °C, and warm air is less dense, so
  QNH comes out higher than the true sea-level pressure, by about 0.008 hPa
  for each metre of the airport's elevation (0.3 hPa at Senai, 38 m). So we
  take QNH + 0.5 hPa (the middle of the hPa it was rounded down from) back up
  to the airport's elevation through the standard atmosphere, and down again
  through the air as the METAR reports it (the hypsometric equation, with the
  virtual temperature from its temperature and dew point). Weighted as
  σ = 0.3 hPa, the spread of a value rounded to 1 hPa. Where the same airport
  sent a SYNOP for that hour, its METAR is dropped: it is the same barometer,
  in coarser steps.

A plane through these points, fitted by weighted least squares, gives
`home_pressure_msl` at home, given at least 3 stations. The meter's altitude
then gives `home_pressure` through the hypsometric equation, with the
virtual temperature of the nearest station that reported temperature and dew
point.

### Why a damped plane

The Singapore airports are all in the north and east of the island, so for
most homes the plane is extrapolated, and a plain least-squares plane
amplifies the 1 hPa steps of the METARs. When one airport's QNH steps by
1 hPa, the plane can tilt by about 1 hPa at home: at 14:00 SGT on
2026-10-17 it gave 1008.6 hPa, while every station read 1009–1010. So the fit has a Gaussian
prior on each component of the gradient: σ = 0.005 hPa/km, about the 0.5 hPa
per 100 km that tropical pressure gradients usually reach (ridge regression).

Over the 168 hours from 2026-10-11 to 18, with the actual reports:

| Fit | Roughness at home | Changi left out | Senai left out | Tanjung Pinang left out |
|---|---|---|---|---|
| Plain plane | 0.65 | −0.13 ± 0.20 | +0.08 ± 0.27 | +0.18 ± 0.33 |
| **Prior σ = 0.005 hPa/km** | **0.22** | **−0.13 ± 0.20** | **+0.18 ± 0.29** | **+0.08 ± 0.23** |
| Prior σ = 0.002 hPa/km | 0.22 | −0.11 ± 0.18 | +0.35 ± 0.41 | −0.22 ± 0.29 |
| Weighted mean (no gradient) | 0.22 | −0.04 ± 0.15 | +0.63 ± 0.69 | −0.59 ± 0.65 |
| Inverse-distance weighting | 0.28 | −0.10 ± 0.30 | −0.06 ± 0.31 | +0.13 ± 0.32 |

All in hPa. Roughness is the rms of each hour minus the mean of its
neighbours. The diurnal pressure tide alone gives about 0.2 hPa of it. "Left
out" is the bias ± rms of predicting a SYNOP station's sea-level pressure from
the others (and not from its own METAR).

The interpolated pressure is good to about 0.2–0.3 hPa (2–3 m of height) at
hours that only METARs cover. Changi's SYNOP, every 3 hours, helps most, since
it is the nearest station with tenths. Smoothing in time would average out
more of the QNH rounding. This is not done yet.

All of `home_pressure*` is recomputed when the poller starts, so a changed
altitude or method applies to the past too. That includes earlier placements
of the meter: the altitude has no history yet.

## Why not

- **NEA / data.gov.sg:** temperature, humidity, rain and wind, but no
  pressure.
- **Open-Meteo and other models:** modelled, not measured (see
  [nea.md](nea.md) for how far its PM2.5 was off).
