# The Oracle

Each finding is computed honestly from your data and interpreted dishonestly.
The dashboard shows it, and `python3 -m aeromancer oracle --range 7d` prints
it.

The one piece of real advice, what to do about stale air, follows the
outdoor air: while NEA's latest PM2.5 (if under 3 h old) is 35 µg/m³ or more,
the dashboard, the Oracle and the Tree of Life stop saying "open a window"
and suggest fewer people and the purifier instead, since airing would trade
CO₂ for particles.

| Finding | What is actually computed |
|---|---|
| Aura | mean CO₂, binned into colors |
| Lunar influence | Pearson correlation of CO₂ with lunar illumination |
| Mercury | share of ≥ 1000 ppm readings taken while Mercury was retrograde (real ephemeris), and its pre- and post-retrograde shadow |
| Chakra residency | time spent in each CO₂ band |
| Natal chart | the Sun's real zodiac sign; mean ppm read as ecliptic degrees |
| Schumann alignment | dominant period from a DFT, in octaves and cents below 7.83 Hz |
| Divine proportion | ratio of time CO₂ spends rising vs falling, compared with φ |
| Life path number | digital root of the mean ppm |
| Voices in the wire | for each undocumented code the meter sends (stored as `op_XX`), its correlation with CO₂, temperature, elapsed time and (over ≥ 7 days) the Moon; the strongest one picks its spirit |
| I Ching | the hexagram of the hour: each line is whether one source rose over the hour before (CO₂, temperature, the purifier's PM2.5, outdoor PM2.5, wind speed; the Moon by waxing), changing if it moved over twice its usual hourly change; a silent source's line is cast by three coins |
| Sensor society | correlation of every pair of series on one grid, with the Sun's height (over ≥ 1 day) and the Moon (over ≥ 7); the lag of the closest pair; who shares a room, from the placements |
| Household choir | the comfort of the last hour, inside and outside, each from its worst guest and their weighted mean (CO₂ above 700 ppm, PM2.5 above 12 µg/m³, VOC, temperature and humidity outside their comfortable bands, wind, rain), picks each side's mode from the brightest (Lydian) to the darkest (Locrian), the tempo and the mood; each guest's leitmotif traces its own line over the window, a scale step per fixed change, in an instrument for what it measures; the tonic from the series' spectral centroids by the Krumhansl–Schmuckler method. *Listen* plays it over the Schumann resonance |
| Souls present | occupants from the CO₂ balance V dC/dt = N·g − Q (C − 425 ppm): Q by regressing dC/dt on C, g = 18 L/h a person, V by the room's name |
| Birth certificates | each source's first reading: its Sun sign, Chinese year (from the new moon that began it) and biorhythms |
| Celestial clock | each series' daily peak, by least squares, in true solar time, as a planet on a horoscope wheel with houses and aspects; the planetary hours from real sunrise and sunset |
| Five elements | NEA's five regions as the five phases (east Wood, south Fire, central Earth, west Metal, north Water): their shares of PM2.5, and which region's PM2.5 moves first |
| Winds | a wind rose of the nearest station on the eight trigrams, the outdoor PM2.5 each wind brought, and the rain |
| Ward | the purifier's PM2.5 against outdoor PM2.5 over the same hours, and how late it follows |
| Horoscope | the last hour's trend and the above, assembled into advice, which never sends you out into the haze |

The dashboard groups the findings by what they read (today, the household,
the heavens, the island, numbers), and lists the main omens under its
header. `oracle` reads the same `nea.toml` as the recorder for the outdoor
findings; without it, or without the purifier, their cards just don't
appear. Planet positions use JPL's approximate Keplerian elements
(Standish), and Mercury's stations land within a day of the published
dates. The Moon uses the mean synodic month. None of it means anything.
