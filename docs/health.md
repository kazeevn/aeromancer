# Google Health (Fitbit, Pixel Watch)

Optionally, the recorder also polls what a Fitbit or Pixel Watch measured
on its wearer, through the [Google Health
API](https://developers.google.com/health), which replaced the Fitbit Web
API in 2026. It needs no packages. The air is what aeromancer is about; the
wearer is data on who breathes it: sleep says when someone is in the bedroom
and breathing slowly, heart rate how hard they work.

## Setup

In the [Google Cloud console](https://console.cloud.google.com/), in a
project with the Google Health API enabled, under Google Auth Platform:

1. Get started: an app name, your email, audience External.
2. Audience → Test users: add the Google account the wearable syncs to.
3. Data Access → Add or remove scopes: filter on "Google Health API" and add
   `googlehealth.activity_and_fitness.readonly`,
   `googlehealth.health_metrics_and_measurements.readonly` and
   `googlehealth.sleep.readonly`.
4. Clients → Create client, of type Desktop app. Download its JSON to
   `~/.config/aeromancer/google-health-client.json` (or pass another file
   with `--health-client`), readable only by you (`chmod 600`).

Then allow access:

```sh
python3 -m aeromancer health-login
```

It opens Google's consent page, catches the redirect on 127.0.0.1, and
saves the refresh token to `~/.config/aeromancer/google-health-token.json`
(`--health-token`). While the app's publishing status is Testing, Google
expires the token after 7 days: run `health-login` again, and the running
poller picks the new one up. A running poller that lost its login logs a
warning every 15 minutes.

With both files present, `run` and `record` poll Google Health every 15
minutes next to the meter; `python3 -m aeromancer health` polls only it.

## What is stored

| Quantity | Data type | Unit, timing |
|---|---|---|
| `health_heart_rate` | `heart-rate` | bpm; every 2–5 s from a Fitbit, about 32 000 a day |
| `health_hrv` | `heart-rate-variability` | RMSSD, ms; every 5 minutes of sleep |
| `health_spo2` | `oxygen-saturation` | %; about each minute of sleep the device trusts |
| `health_steps` | `steps` | steps in the minute that starts there; minutes with none are absent |
| `health_breathing_rate` | `respiratory-rate-sleep-summary` | breaths a minute over the whole sleep, at its end |
| `health_resting_heart_rate` | `daily-resting-heart-rate` | bpm; one a day, at local midnight |
| `health_skin_temperature`, `health_skin_temperature_baseline` | `daily-sleep-temperature-derivations` | °C, the night's wrist temperature and the device's baseline; one a day, at local midnight |
| `health_sleep` | `sleep` | the stage from each stage's start on (below) |

`health_sleep` holds, from each stage's start, 1 awake, 2 REM, 3 light,
4 deep, and 0 from the end of the sleep, or while out of bed, if the device
says. A "classic" sleep, recorded when the stages can't be told apart (a
short nap, a loose band), has 1 awake, 1.5 restless and 2.5 asleep. The
dozen or so short awakenings a night, which the API lists apart and which
overlap the stages, are not stored.

The phone's own step count (device "MobileTrack") is dropped: it counts the
same walks as the wearable, minute for minute.

The phone syncs the wearable's data in batches, and sleep is reprocessed
after waking, so each poll re-reads each data type from 6 hours before its
newest stored reading, and replaces what is stored there; a sleep is
replaced whole. The first poll backfills 30 days, which for heart rate is
about 200 requests and 10 minutes.

## Notes on the API

- Filters name the data type with underscores, as `heart_rate.sample_time.physical_time`,
  not in the camelCase of the JSON field (`heartRate`), which the API
  refuses as `INVALID_DATA_POINT_FILTER_DATA_TYPE_RESTRICTION`.
- A page of heart rate holds about 5000 points, whatever `pageSize` asks.
- Points come newest first.

## Privacy

This is health data. It stays in the local database, and the dashboard
and the analyses don't show it yet.
