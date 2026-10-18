# Blueair "CO2" is an estimate from the VOC sensor

The Blueair Classic 490i ("Kent") reports a `co2` value through its cloud, which we store as
`blueair_co2`. It isn't a measurement. The purifier has no infrared CO2 sensor like the zyTemp
meter's. The number is an *equivalent* CO2 (eCO2) that the firmware calculates from its gas
(VOC) sensor. This is probably why the Blueair app doesn't show it.

## What Blueair says

- The Classic 400 series manual lists the 480i/490i's sensors as "PM2.5, VOC, temperature and
  humidity". CO2 isn't on the list.
- Retail listings for the Classic i-series describe the CO2 figure as "equivalent based on
  VOC-level". Blueair's Aware monitor is likewise sold as measuring "carbon dioxide equivalents".
- Neither the manual nor anything found online says which gas sensor chip the purifier uses, or
  where on the unit it sits. For cleaning, the manual separates "the air inlet grille" from "the
  small air inlets", which may be the sensor openings.
- The cloud's device info has an `aimSerialNumber` field with an `aimUpdateDate`. "AIM" may be
  the air-quality sensor module, but this is unconfirmed. (Its `roomLocation` field says
  `kitchen`, but that is a placeholder the owner didn't set; it isn't where the purifier is.)

## How eCO2 is usually calculated

Gas sensors of this kind have a heated metal-oxide film whose resistance drops in the presence of
gases such as VOCs or hydrogen. They can't tell these gases apart and can't detect CO2 at all.
Typical firmware works like this:

1. It learns a clean-air reference. On the ams CCS811, this is by default the highest resistance
   seen in the last 24 hours. That reference is defined as **400 ppm eCO2 / 0 ppb TVOC**, so eCO2
   never goes below 400. The CCS811 documentation says the room needs airing daily, or the
   reference shifts.
2. It converts the change from that reference into a CO2 figure, assuming that people breathe out
   CO2 together with VOCs and hydrogen. Sensirion's SGP30 bases its eCO2 on hydrogen; Bosch's BSEC
   library for the BME680 bases its "CO2 equivalent" on breath VOCs. The exact formulas are
   proprietary.
3. The first readings after power-on are fixed at 400 ppm / 0 ppb while the sensor warms up.

An independent comparison found eCO2 reproducible under similar conditions but not
quantitatively reliable.

## What our data shows

Data: 293 paired `blueair_co2` / `blueair_voc` readings at 5-minute intervals, from 2026-10-16
19:37 to 2026-10-17 19:58 local time.

- **Floor at exactly 400 ppm.** Exactly 400 is the most common value. A real CO2 sensor would
  vary a little around that level instead of stopping at it.
- **Strong correlation with VOC.** Pearson r = 0.85 and Spearman ρ = 0.87. Leaving out the
  readings at the floor changes almost nothing: with CO2 > 400, n = 281 and r = 0.85. The 5-minute
  *changes* in the two also correlate at r = 0.85, with the best match at zero delay.
- **Not a fixed function of VOC.**
  - The best straight line, CO2 ≈ 0.26·VOC + 347, explains only R² = 0.71 of the variation, with
    a typical miss of ±50 ppm. Fitting against ln(VOC) does worse (R² = 0.25).
  - The same VOC level gives different CO2 at different times: VOC ≈ 525 matched 480 ppm at 03:00
    but 403 ppm at 14:00.
  - From 10:30 to 13:50, VOC stayed at 530–610 while CO2 fell from 586 to 405 and then stayed at
    the floor. This fits the clean-air reference adapting to the current air.
  - The relationship flattens at the top. At 08:22, VOC went from 908 to 2495 (about 3×) while CO2
    went only from 616 to 771.
  - A model with a drifting reference, CO2 ~ VOC − (moving average of VOC), fit worse than the
    plain straight line for every averaging period from 1 to 24 h. So the drift has some other
    form.
- **Step at 18:17.** VOC fell from about 290 to 1–24 within one interval, and CO2 went to 400–406.
  This looks like the reference being reset, though a real change in the air can't be ruled out.
  Blueair's VOC readings don't seem to share the eCO2 reference: VOC stayed around 540 while CO2
  was at the floor.

## Two weeks of hourly history

On 2026-10-17 the cloud returned hourly means for 14 days, from 2026-10-03 20:23 (asked with
`seconds_ago` = 14 days and `sample_period` = 3600; not stored).

- **Daily cycle.** eCO2 climbs through the evening and night, often to 1000–1500 ppm and up to
  3798 ppm (10-10 01:23). It then falls back to 400 by about 13:00–16:00 nearly every day. Indoor
  PM2.5 does the opposite: it peaks around midday (often 80–145 µg/m³) while eCO2 sits at the
  floor. This fits windows or doors open in the daytime, letting in hazy outdoor air and diluting
  VOCs, and a closed, occupied room at night. Real CO2 would follow the same pattern, so the
  zyTemp is needed to tell the two explanations apart.
- **VOC extremes.** Hourly means reach 15,315 (10-13 19:23), at the same time as eCO2 2947–3747.
- **Near-zero VOC is unusual.** Before 10-17, VOC dipped near zero for only an hour or two
  (12.8 at 10-04 10:23, 78 at 10-10 16:23). Since the step at 10-17 18:17 it has stayed at 4–24
  for hours, which is unprecedented in the two weeks. Either the sensor's reference reset, or it
  stopped responding. A deliberate VOC source near the intake would tell which (see
  [ideas](ideas/ideas.md)).

## How far back the cloud goes

Blueair doesn't publish a retention period. On 2026-10-18 we asked the cloud for longer and
longer windows:

- **The cutoff is 42 days.** A window of 41.98 days returned points from 2026-09-06 13:34. Any
  longer window, even 42.01 days, returned nothing at all rather than a trimmed list.
- **It is the same at every resolution.** Daily, hourly and 5-minute averages all reach back
  42 days. A 30-day window at 5 minutes returned 7,856 of 8,640 possible points, with gaps but
  no coarsening.
- **This may be a limit on requests, not on storage.** The API takes only "the last N seconds",
  with no start date, so we can't tell whether older data is deleted or just can't be asked for.
  Either way, nothing older than 42 days can be retrieved.
- **The settings have no history.** Fan speed and auto mode exist only as current values.

So anything older than six weeks exists only in our own recording.

## Side by side with the zyTemp

On 2026-10-18 from 00:22 to 13:04, the zyTemp sat on the bedroom floor next to the purifier's air
intake (see the placements table). Data: 148 five-minute `blueair_co2` readings from 00:30 to
13:04, each paired with the mean of the zyTemp readings within ±2.5 minutes.

| | zyTemp (CO2) | Blueair eCO2 |
|---|---|---|
| Range | 623–1162 ppm | 400–675 ppm |
| Mean | 987 ppm | 441 ppm |
| At exactly 400 ppm | — | 39% of readings |

- **Far too low.** eCO2 was about 550 ppm below real CO2 on average. The room was stuffy, around
  1000 ppm, all night, and eCO2 never showed it.
- **Doesn't follow real CO2.** Pearson r = 0.27 and Spearman ρ = 0.26. The 5-minute changes
  correlate at r = 0.09, against r = 0.87 with the Blueair's own VOC.
- **Real CO2 peaked while eCO2 sat at the floor.** From 03:00 to 04:00 the zyTemp read
  1121–1162 ppm while eCO2 read 400–404. When real CO2 was above 1050 ppm (n = 45), eCO2 averaged
  459 ppm.
- **VOC events still show.** At 11:00, VOC rose to 5117 and eCO2 to 675, while real CO2 stayed at
  846–886 ppm.

After this, the dashboard stopped showing `blueair_co2`; it is still recorded.

## Conclusion

Treat `blueair_co2` as a smoothed VOC index, scaled to ppm and measured against a reference that
drifts. It's good for spotting events like cooking, cleaning or people arriving. It can't measure
ventilation, and it shouldn't be compared with the zyTemp as if both measured CO2. Side by side,
it missed a whole night of stuffy air.

## Open questions

- What form does the eCO2 reference drift take, and how often does it reset? A step like the one
  at 18:17 should recur, maybe daily.
- Gas cooking produces real CO2 *and* VOCs, so near a gas stove the two can rise together for
  reasons that have nothing to do with how eCO2 is calculated.

## Sources

- [Blueair Classic 400 series manual (480i/490i)](https://aimg.as-1.co.jp/c/64/5175/40/64517539manual.pdf)
- [Blueair Classic 680i listing ("equivalent based on VOC-level")](https://page2flip.de/?p=38498852)
- [Blueair Aware](https://www.blueair.com/ph/air-purifier-filters/aware/global-1561.html)
- [TVOC and eCO2 sensors: CCS811 baseline, reliability test](https://wolles-elektronikkiste.de/en/tvoc-and-eco2-sensors)
- [Adafruit SGP30 guide](https://learn.adafruit.com/adafruit-sgp30-gas-tvoc-eco2-mox-sensor?view=all)
- [ESPHome BME680 via BSEC](https://esphome.io/components/sensor/bme680_bsec/)
