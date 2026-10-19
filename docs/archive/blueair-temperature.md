# Blueair temperature reads warm from its own fan

The Blueair Classic 490i's `blueair_temperature` reads 2–4 °C above the zyTemp's `temperature`.
The purifier heats its own sensor: most of the gap comes and goes with the fan, within about
15 minutes. With the fan off, about 0.9 °C remains, which is within the zyTemp's rated accuracy.

## Side by side

On 2026-10-18 and 10-19 the zyTemp sat on the bedroom floor about 10 cm from the purifier's air
intake (see the placements table), so both measured the same air. Data: each 5-minute
`blueair_temperature` upload in two such periods, of about 12 and 18 hours, paired with the mean
of the zyTemp's readings in the 5 minutes before it, and with the fan speed last polled. The AC
was on for nearly all of it.

| Fan speed | n | Blueair − zyTemp, median | sd |
|---|---|---|---|
| 1 | 193 | 2.79 °C | 0.15 |
| 2 | 108 | 2.47 °C | 0.25 |
| 3 | 54 | 1.96 °C | 0.34 |

- **The gap is steady at a given speed.** Its sd at speed 1 is 0.15 °C.
- **It follows the fan, not the room.** At a change of speed, the Blueair moves at once and the
  zyTemp doesn't. Three examples, as means over 20 minutes before against 5–25 minutes after:

  | Fan | Blueair | zyTemp |
  |---|---|---|
  | 2 → 1 | +0.50 | −0.02 |
  | 1 → 2 | −0.43 | +0.02 |
  | 2 → 1 | +0.56 | +0.01 |

- **Both follow the room.** When the room cooled by about 0.8 °C one night, and warmed by about
  2 °C after the AC was switched off, both moved by about as much, and the gap stayed.

## Fan off, then speed 1

On 2026-10-19 the purifier was set from the cloud to manual, fan 0 at time T and speed 1 at
T + 60 min, and back to auto at T + 120 min. The AC had been switched off at T − 57 min. The
zyTemp stayed at the intake, and the door and window stayed closed.

| Time | Fan | Blueair | zyTemp | Gap |
|---|---|---|---|---|
| T − 3 min | 2 | 31.00 | 27.85 | 3.16 |
| T + 2 min | 0 | 30.95 | 27.85 | 3.10 |
| T + 7 min | 0 | 29.49 | 27.80 | 1.69 |
| T + 12 min | 0 | 28.75 | 27.75 | 1.00 |
| T + 17 to 58 min | 0 | 28.50–28.57 | 27.67–27.73 | 0.80–0.89 |
| T + 63 min | 1 | 29.03 | 27.73 | 1.29 |
| T + 68 min | 1 | 30.88 | 27.78 | 3.09 |
| T + 78 to 113 min | 1 | 31.77–31.86 | 27.92–28.16 | 3.70–3.86 |

- **About 3 °C came from the fan running at speed 1.** The gap fell from 3.1 to 0.8 °C when the
  fan stopped and rose to 3.8 °C when it restarted. Each time it settled within about 15 minutes,
  so the source of the heat is small and close to the sensor, not the whole case warming up.
- **About 0.9 °C remained with the fan off,** steady for 40 minutes. It could be the electronics
  that stay on (Wi-Fi, controller, sensors), a calibration offset in either device, or both: the
  zyTemp alone is rated ±1.5 °C. A third thermometer would tell them apart.
- **The gap at speed 1 was larger with the AC off:** 3.8 °C, against 2.8 °C with it on. The AC's
  draft probably also cooled the purifier's case.
- **At speed 1 the Blueair barely followed the room.** From T + 88 to T + 113 min the zyTemp
  rose 0.16 °C and the Blueair 0.04 °C. With the fan off it followed the room as closely as the
  zyTemp. Unexplained.
- **A first run agrees.** On 2026-10-18 the fan was set to 0 for 31 minutes, for a filter decay
  test, while the zyTemp was in the living room. The Blueair fell from 27.9 to 26.4 °C within
  15 minutes, then rose to 31.1 °C at speed 1.

## Why it can't be the airflow being warmed

All of both devices' power ends up as heat in the room, but the room's warming reaches both
sensors alike. Only the heat that reaches the purifier's sensor before it mixes in makes a gap,
and the power ratings bound how much that can be if it's carried by the main airflow:

- The purifier draws 15 W at the lowest speed and 90 W at the highest (Blueair's figures; none
  per speed or for standby).
- At speed 1 it moves about 130 m³/h (the `airflow` setting in [blueair.md](../blueair.md)).
  Warming that by 1 °C takes 130/3600 m³/s × 1.18 kg/m³ × 1005 J/(kg·K) ≈ 43 W.
- So even all 15 W in the air stream warms it by at most 0.35 °C, and 90 W at about 520 m³/h by
  at most 0.5 °C.

The gap at speed 1 is 2.8–3.8 °C, many times that. The sensor must sit where little air moves,
close to the motor or its driver, so that more air (higher speeds) cools it more and stopping
the motor removes most of the heat.

The zyTemp (MasterKit MT8057S) draws 20 mA on average and 200 mA at peak from USB's 5 V, about
0.1 W. Inside its small case that might warm its sensor by a few tenths of a degree (an estimate,
not measured), which would make it read high, not low. Its manual gives ±1.5 °C accuracy and
20–30 minutes to settle after a change.

## Humidity

`blueair_humidity` moved the opposite way to the Blueair's temperature: from 60.5 to 63.8 % when
it fell 2.5 °C at fan 0, and from 64.5 to 61.7 % when it rose 2.9 °C at speed 1. At constant
moisture, relative humidity changes by about 6 % of itself per °C, so a sensor heated as much
as the temperature sensor would have moved about three times as far. The humidity sensor is
either a little apart from the heat, or the firmware corrects for it.

## CO2 while the fan was off

The zyTemp's CO2 rose from about 575 to 624 ppm with the fan off, which first looked like CO2
gathering near the floor without the purifier stirring the air. It kept rising with the fan at
speed 1, to 690 ppm by T + 98 min, so it was the room, most likely someone in it with the AC
off. Gravity separates CO2 from air very little at room scale, and exhaled breath is warm and
rises.

## Conclusion

Treat `blueair_temperature` as the room's temperature plus the purifier's own heat: about 0.9 °C
with the fan off, about 2–4 °C running, more at low speed, and more with the AC off. Its changes
follow the room when the fan speed and the AC stay the same. Use the zyTemp for the room's
temperature.

## Open questions

- Which device carries the 0.9 °C left with the fan off? Check the zyTemp against the outdoor
  stations (see [ideas](../ideas/ideas.md)).
- Why did the Blueair stop following the room at speed 1, from T + 88 min?

## Sources

- [Blueair Classic 490i](https://www.blueair.com/en-id/products/classic-490i) (15–90 W)
- [Blueair Classic 480i](https://www.blueair.com/us/pdp-2931.html) (15 W lowest, 90 W highest)
- [MT8057S manual](https://dadget.ru/upload/iblock/c65/c65160b9b662430d6f24631ac4772b0c.pdf)
  (in Russian: current, temperature accuracy, settling time)
