# What the zyTemp's undocumented codes mean

The meter is a MasterKit MT8057S (Dadget), firmware 2105, USB `04d9:a052`, `bcdDevice` 2.00. It
sends each frame in plaintext, so the key we set doesn't matter. Besides CO2 (`0x50`) and
temperature (`0x42`), it sends eight more codes in its normal cycle and a dump of 52 items at
power-up. The recorder stores them as `op_XX`. This study works out what they are.

## What is published

Nobody has decoded them. On 2026-10-18 we searched sources in English, German, Russian, Japanese
and Chinese, and the code and issues of about 30 projects. Every library and write-up calls the
extra codes "unknown".

- **The official documents define few items.** ZyAura's ZG01/ZG01C manuals, the ZG106 firmware
  spec and CO2Meter's AN135/AN146 define only `P` (0x50, CO2), `B` (0x42, temperature), `A`
  (0x41, humidity), `Z` (0x5A, firmware version) and `]` (0x5D, writable zero calibration).
- **revspace guessed at three codes.** On a related ZyAura unit, revspace.nl noted that 0x71 is
  "always close to" CO2 and 0x6D "seems to always have same value". It asked whether 0x52/0x56
  are "barometric pressure?".
- **Henryk Plötz found no meaning, but a lead.** In his reverse engineering (hackaday.io 5301) he
  logged the codes without interpreting them. He noted that the vendor's Windows software parses
  more codes than 0x50 and 0x42.
- **nikvoronin logged a power-up dump.** nikvoronin/Co2.Monitor captured one of an MT8057, with no
  interpretation.

## Data

- **19 hours of recording.** 13,000 cycles from 2026-10-17 18:55 to 2026-10-18 13:46 SGT. CO2 was
  556–1370 ppm and temperature 24.0–26.7 °C.
- **An hour of raw frames.** On 2026-10-18 from 14:27, every frame was logged, including three
  power-up dumps, with these tests:
  - the altitude set to 0, 5200 and 9800 m;
  - one breath on the meter, which drove CO2 past the top of its range.

## The normal cycle

Every 5 s the meter sends:

`6D 6E 71 50`, then either `4F 52` or `57 56` (alternating), then `41 43 42`

- 0x41 (humidity) is always 0: this model has no humidity sensor.
- 0x4F/0x52 and 0x57/0x56 therefore come every 10 s.
- 0x6E and the CO2 value also change only every 10 s.

| Code | What it is | Confidence |
|---|---|---|
| 0x43 | Temperature sensor reading, about 10× finer than 0x42 | High |
| 0x6E | Filtered NDIR absorption signal; CO2 is calculated from it | High |
| 0x71 | CO2 before the temperature, offset and altitude corrections; clamped at about 3507 | High |
| 0x4F | Raw CO2-sensitive sample, one per measurement | Medium |
| 0x52, 0x56 | One CO2-independent raw quantity, sampled on alternate measurements: probably the reference beam or lamp intensity | Medium |
| 0x57 | Another CO2-independent raw quantity, sampled together with 0x56 | Low |
| 0x6D | A slow internal temperature, probably the NDIR module's body | Low–medium |

### 0x43: fine temperature

- **0x42 follows 0x43 exactly.** 0x42 = 0.1006·0x43 + 4414 (0x42 is in 1/16 K). The scatter is
  0.30 counts, which is just 0x42's rounding to whole counts.
- **In °C:** T ≈ 0.00629·0x43 + 2.73 °C.
- **The formula carries over to other units.** It reproduces other people's published samples to
  within 0.3 °C: Henryk's 3231 → 23.0 °C (his 0x42: 23.3 °C), revspace's 2964 → 21.4 °C (21.1 °C).
- **It is the fastest channel to react.** When the meter is picked up, it responds to the warmth
  of a hand at once.

### 0x6E, 0x71 and CO2: the processing chain

1. **0x6E is the filtered absorption signal.** It falls as CO2 rises (r = −1.00).
   - A smooth cubic of 0x6E gives the CO2 output to 0.98 ppm, or 0.72 ppm when temperature is
     added. One count is about 0.43 ppm.
   - Its level differs between units: it reads 17,000–21,000 in published dumps and about 27,000
     on ours.
2. **0x71 is CO2 at the sensor.**
   - It is clamped: during the breath test 0x6E kept falling, from 23,227 to 17,979, while 0x71
     stayed at 3507–3509.
3. **0x50 is 0x71 after three corrections:**

   **0x50 = F(h) · 0x71 · (0.9005 + 0.004506·T[°C]) + 46**

   The corrections are:
   - **Temperature: about +0.44 %/K, which is 1.014 at 25 °C.** For comparison, an ideal-gas
     density correction would be 0.34 %/K.
   - **A fixed +46 ppm offset, added last.** It isn't the zero-calibration item: `]` (0x5D) is 0.
     It might be an automatic baseline correction. If so, it would change over days.
   - **F(h), the altitude factor (see below).** h is the altitude setting.

   Over 13,000 cycles at h = 0 the formula misses by 0.33 ppm, which is just rounding.

### 0x4F, 0x52, 0x56, 0x57: raw samples

- **They are noisy raw samples.** Each changes in about 91 % of updates. Successive steps are
  anti-correlated (lag-1 r ≈ −0.4; white noise gives −0.5). 0x6E and CO2 are smooth instead.
- **Each pair is sampled together.** Their high-frequency noise correlates within the pair (0x4F
  with 0x52: r = 0.32; 0x57 with 0x56: r = 0.35) but not across cycles. So each pair is probably
  read on the same lamp pulse.
- **0x4F follows CO2.** It rises with CO2 (r = 0.97), whereas 0x6E falls.
  - CO2 predicted from 0x4F alone misses by 28 ppm.
  - Subtracting a share of 0x52 cuts that to 11 ppm, so 0x52 acts as a reference.
  - Neither reproduces 0x6E exactly. The firmware's path from these samples to 0x6E is unknown.
- **0x52 and 0x56 are the same quantity.** They track each other within about 0.2 % on our unit
  and on every published unit, though their level varies a lot from unit to unit. They don't
  follow CO2.
  - After a replug they jump by 30–50 counts and settle over about 10 minutes.
  - Their correlation with the temperature trend is weak (|r| ≤ 0.36).
- **They are not air pressure.** We compared hourly means over 22 hours with `home_pressure`
  (see [pressure.md](../pressure.md)), which swung by 3.9 hPa (1004.9–1008.8). We left out the
  test hour and the 15 minutes after each replug.
  - With temperature and CO2 accounted for, 0x52 moves 4.4 counts per hPa and 0x56 1.3. If they
    were pressure (proportional, or in 0.1 hPa units), both would move 10–12 counts per hPa, and by
    the same amount.
  - Adding pressure barely improves the fit: the hourly scatter of 0x52 drops from 13.8 to 13.0
    counts, and that of 0x56 from 10.4 to 10.3.
  - A phone barometer logged 15:20–17:20 alongside the meter, but the pressure moved only
    0.36 hPa and every channel shared one trend there, so it can't tell them apart.
- **0x57 moves with 0x56** (r = 0.96 at the minute scale).
- **No CO2 or humidity in them.** None of the four improves CO2 predicted from 0x6E. They didn't
  follow the purifier's humidity readings, which ranged from 58 to 68 %.

### 0x6D: slow internal temperature

- **It is nearly constant:** 3240–3259, rising about 5 counts per kelvin.
- **It lags far behind the air temperature.**
  - After a replug with the meter warm from handling, 0x43 read 26.4 °C at once, while 0x6D took
    about 14 minutes to rise from 3248 to 3258.
  - It fell as the meter cooled.
- **It also drifts slowly:** about 5 counts overnight at a steady air temperature.
- **Its level differs between units:** 994 to 3259 in published samples.

## The altitude setting

The MT8057's rear buttons set the altitude above sea level. The power-up dump reports it as
**0x4D, in metres**. We tested this on 2026-10-18:

| Setting | 0x4D after the next power-up | Measured F |
|---|---|---|
| 0 m | 0 | 1 |
| 5200 m | 5200 | 1.9205 (fitted over 0x71 = 566–2827, scatter 0.6 ppm) |
| 9800 m | 9800 | 3.095 |

- **The new setting acts at once.** 0x50 jumps within one cycle, and 0x71, 0x6E and the raw
  channels don't move.
- **F multiplies the sensor CO2, not the +46 offset.** At 5200 m, fitting the offset freely gives
  46.0.
- **F follows the standard atmosphere only part way.**
  - The standard-atmosphere pressure ratio, P₀/P = (1 − 2.25577·10⁻⁵·h)^−5.256, gives 1.927 at
    5200 m, close to the 1.9205 measured, but 3.72 at 9800 m.
  - The isothermal formula exp(h / 8434 m) gives 1.853 and 3.196: wrong at both.
  - The datasheet's "0.13 % of reading per mmHg" gives 1.475 at 5200 m: wrong too.
- **A quadratic in pressure fits both points:** P/P₀ ≈ 1 − 1.183·10⁻⁴·h + 5.0·10⁻⁹·h².
  - Its linear term matches the standard atmosphere's slope at sea level, 1.186·10⁻⁴ per m.
  - So near sea level the correction is the standard-atmosphere one. Higher up, the firmware
    seems to use a cruder approximation.
  - Two points can't pin down the formula.

**What this means at home.** The meter sits at 32.1 ± 2.5 m above sea level. This was measured with
a phone barometer against the Changi airport pressure reports.
- At a setting of 0 m it reads 0.38 % low (−3.8 ppm at 1000 ppm).
- At 100 m it read 0.8 % high.

The meter had been at 0 m all along, and was set back to 0 m after the test.

## The power-up dump

About 1 s after the meter is plugged in and a host sets the key, the meter sends 52 items, one
every 80 ms, before the normal cycle starts. A host that opens the device later misses the
beginning. Some codes (0x41, 0x6E, 0x71) mean something different here than in the normal cycle.

Our unit's values are below; most are identical on nikvoronin's MT8057.

| Code | Ours | nikvoronin | Note |
|---|---|---|---|
| 0x62, 0x63, 0x64 | 16656, 34, 3411 | not captured | |
| 0x28, 0x29, 0x26, 0x25 | 5475, 5705, 7383, 10640 | same | |
| 0x71 | 0 | same | |
| 0x45 | 32767 | same | |
| 0x79 | 65255 (−281) | same | |
| 0x75 | 4640 | same | |
| 0x2E | 1200 | same | yellow → red threshold, ppm |
| 0x41 | 17280 | same | |
| **0x47** | **4470** | 886 | per unit |
| **0x49** | **7428** | 2666 | per unit |
| 0x72, 0x69, 0x4B | 19494, 6570, 19959 | same | |
| 0x51 | 513 | same | |
| 0x6F | 50000 | same | |
| **0x6C** | **2105** | 2101 | firmware version (ZyAura numbers firmware like "2103") |
| **0x76** | **30026** | 24596 | per unit |
| **0x77** | **6043** | 4750 | per unit |
| 0x7A, 0x78 | 4053, 0 | same | |
| 0x53, 0x3D, 0x60, 0x54, 0x7B | 9830, 32768, 15859, 8781, 2621 | same | |
| 0x55 | 190 | same | |
| **0x4E** | **3170** | 3463 | per unit |
| 0x3A | 1025 | same | |
| 0x58 | 25439 | same | |
| 0x70 | 3000 | same | range, ppm |
| 0x73, 0x2F | 2565, 4915 | same | |
| 0x68 | 800 | same | green → yellow threshold, ppm |
| 0x4C | 0 | same | |
| 0x3B, 0x5B, 0x65 | 400, 400, 400 | same | 400 ppm baseline? |
| 0x5D (`]`) | 0 | same | zero-calibration offset |
| 0x5E | 65523 (−13) | same | |
| 0x66 | 0 | same | |
| **0x4D** | **0 / 5200 / 9800** | 100 | **altitude setting, m** |
| **0x59** | **353** | 498 | per unit |
| 0x6E | 30 | same | |
| 0x5C | 2000 | same | |
| **0x74** | **47248** | 40703 | per unit |
| 0x4A, 0x48 | 711 / 710 / 711, 3801 / 3799 / 3797 | not captured | change slightly between boots: live values? |

The per-unit items are probably calibration constants. The teardown of a CO2-mini found a 93C66
EEPROM.

## Side effects for the recording

- **The first frames after power-up are stale.** They repeat old values held in the sensor's
  filter. Examples:
  - 0x71 = 3507 → 0x50 = 6872 at 5200 m, and 11077 at 9800 m;
  - 0x71 = 1156–1189 → 0x50 = 2366–3696;
  - and on 2026-10-18 at 13:04, 1370 ppm instead of about 680.

  They pass the recorder's 10,000 ppm plausibility limit.
- **The test made some CO2 readings meaningless.** CO2 recorded on 2026-10-18 from 14:39 to 15:06
  SGT is inflated: ×1.92, then ×3.10, plus the breath spike. Leave it out of any analysis.

## Open questions

- **What are 0x52/0x56 and 0x57?** Not pressure (see above). The reference beam or lamp
  intensity remains the best guess.
- **What is the exact altitude formula?** Settings of 1000, 2000 and 3000 m would show its shape.
- **What is the +46 ppm offset?** If it drifts over days, it is an automatic baseline correction.
- **How does the firmware get from 0x4F/0x52/0x56/0x57 to 0x6E?** And what is 0x57 physically?
- **What do the vendor's codes mean?** Disassembling the vendor's Windows software (ZG.exe) would
  give its own names for the codes.

## Sources

- [revspace.nl: CO2MeterHacking](https://revspace.nl/CO2MeterHacking)
- [Henryk Plötz: Reverse engineering a low-cost USB CO₂ monitor](https://hackaday.io/project/5301-reverse-engineering-a-low-cost-usb-co-monitor)
- [nikvoronin/Co2.Monitor](https://github.com/nikvoronin/Co2.Monitor): MT8057 power-up dump
- [ZG01 module manual](https://revspace.nl/images/2/2e/ZyAura_CO2_Monitor_Carbon_Dioxide_ZG01_Module_english_manual-1.pdf)
- [CO2Meter AN146, RAD-0401 serial communication](http://co2meters.com/Documentation/AppNotes/AN146-RAD-0401-serial-communication.pdf):
  the `]` zero calibration
- [CO2Meter AN135, USB protocol for CO2mini](https://github.com/leorbs/airco2ntrol/blob/HEAD/resources/AN135-CO2mini-usb-protocol.pdf)
- [MasterKit on Habr: the MT8057](https://habr.com/ru/companies/masterkit/articles/248403/)
  and [its altitude buttons](https://habr.com/ru/companies/masterkit/articles/378895/)
- [CO2-mini teardown](https://donadona.hatenablog.jp/entry/2021/01/11/114156)
- [Dadget MT8057S](https://dadget.ru/catalog/datchiki_kachestva_vozdukha/detektor_uglekislogo_gaza/)
  and [its manual](https://dadget.ru/upload/iblock/c65/c65160b9b662430d6f24631ac4772b0c.pdf)
