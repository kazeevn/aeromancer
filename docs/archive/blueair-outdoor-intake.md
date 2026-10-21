# Blueair outdoor intake: its sensors read a mix, not the stream

With the Blueair Classic 490i set up to draw mostly outside air (`--outdoor-intake`), the air it
blows out is mostly outside air, filtered. Its own sensors read far less PM2.5 than outside, and
humidity closer to the room's. The sensors don't sample the main stream: they read a mix of room
air and outside air, and the faster the fan runs, the more outside air is in it. Particles
aren't lost from the air on the way to the sensor.

Data: the 5-minute uploads in the outdoor-intake placements from 2026-10-19 to 10-21, NEA's
hourly PM2.5 (mean of the west, south and central regions) and its stations' temperature and
humidity. The manual puts the air inlet on the right side and the outlet on the left; the
sensors' "small air inlets" are mentioned for cleaning but not located.

## The main stream is mostly outside air

On 2026-10-21 the zyTemp hung in the purifier's outlet read 450–455 ppm CO₂ at speed 3 and
469–482 ppm at speed 1, against about 425 ppm outdoors and 550–600 ppm in the room just before.
So the outlet air was about 60–75 % outside air at speed 1 and 80–85 % at speed 3.

## The sensor reads much less, more with the fan

Its PM2.5 against NEA's, in the two outdoor-intake periods (the second set up anew):

| Period | Speed | Purifier PM2.5 | NEA | Ratio |
|---|---|---|---|---|
| 2026-10-19 to 10-20 | 1 | 19–27 | 80–82 | 0.25–0.35 |
| | 2 | 25–31 | 73–82 | about 0.35 |
| | 3 | 36–46 | 74–76 | 0.5–0.6 |
| 2026-10-20 to 10-21 | 1 | 5–9 | 50–69 | 0.08–0.15 |
| | 3 | 30–37 | 56–61 | 0.55–0.6 |

Each speed set by hand moved the reading within one or two uploads, both ways:

| Date | Speed | Before | After |
|---|---|---|---|
| 2026-10-19 | 1 → 3 | 24–30 | 36–43 |
| 2026-10-19 | 3 → 2 | 49–52 | 37–40 |
| 2026-10-20 | 2 → 1 | 31–34 | 19–24 |
| 2026-10-21 | 1 → 3 | 9–10 | 26–29 |
| 2026-10-21 | 3 → 1 | 35–37 | 13–19 |

The room's air can't change that fast in both directions; what the sensor draws does. The one
speed set by hand from 1 to 3 in a closed room (bedroom, 2026-10-19), where the room's PM2.5
could only fall, raised the reading by about a third, from 29–31 to 36–45. So part of each step
may be the sensor itself reading more at a higher speed, but most of a 2.5–3× step is a change
in which air reaches it.

## The sensor reads outside air right when it gets it

On 2026-10-20, at speed 1 and with a door open to the outside, the reading rose from 18–20 to
73–77 µg/m³ within one upload, against NEA's 82 that hour. Its PM1/PM2.5 then was 0.70–0.73.

| Condition | PM1/PM2.5 |
|---|---|
| Outside air, door open, speed 1 | 0.70–0.73 |
| Outdoor intake, speed 1 | 0.75–0.82 |
| Room, speed 1 | 0.78–0.85 |
| Outdoor intake or room, speed 3 | 0.92–0.95 |

At speed 1 the outdoor intake reads like the room, not like outside air. The rise at speed 3
happens in both setups, and within an upload of the change. It could be the sensor's inlet
letting in fewer 1–2.5 µm particles at a higher flow, which would take at most a quarter off
PM2.5, but the purifier splits its counts into PM1 and PM2.5 in firmware, so it is weak
evidence. It can't explain a three- to tenfold gap at speed 1, where the ratio is the room's.

## Humidity agrees

In the second period, the dew point from the purifier's own temperature and humidity was
19–22 °C at speed 1, against
25.7–26 °C outdoors; the AC kept the room drier. In the hour at speed 3 it rose from 20.0 to
21.8 °C, and fell back after. Its humidity sensor is heated less than its temperature sensor
([temperature study](blueair-temperature.md)), so the dew point is biased by up to a degree or
two, more at low speed.

## Why particles can't be separated from the air

Haze is mostly particles below 1 µm, which follow the air. A particle's relaxation time is
`ρ d² C / 18μ`: 5 µs for 1 µm and 30 µs for 2.5 µm, at 1.5 g/cm³. At 5 m/s they coast 30 µm and
0.15 mm before following a turn of the air, and through the inlet grille the air moves at
0.3–1.2 m/s (130–520 m³/h through about 0.1 m²). The openings are millimetres to centimetres
across, so haze goes wherever the air goes. Only the largest particles that PM2.5 counts could
miss a small inlet in a fast cross-flow. Settling is 0.05–0.3 mm/s, nothing over a purifier's
height.

## Conclusion

With an outdoor intake, the purifier's sensors read a mix of room and outside air. At speed 1 it
is mostly the room's; at speed 3 about half and half. How much depends on the setup as well:
the same speed read 0.25–0.35 of NEA in one period and 0.08–0.15 in the next. Use neither as the
outside air's PM2.5, nor as the room's.

## Open questions

- Where are the sensors' small air inlets? At speed 1, hold a smoking incense stick or an open
  bottle of hand sanitizer for a minute at each candidate spot, and see which one makes PM2.5 or
  VOC spike at the next upload. Then the zyTemp's CO₂ at that spot gives the share of outside air
  there. If it reads like outside air while PM2.5 stays low, particles are lost after all.
- How much does the sensor itself read more at a higher speed? Set the speeds 1, 3, 1 by hand in
  a closed room, about 20 minutes each, and compare the steps with the room's decay.

## Sources

- [Blueair Classic 400 series manual (480i/490i)](https://aimg.as-1.co.jp/c/64/5175/40/64517539manual.pdf)
  (air inlet on the right side, outlet on the left; "the small air inlets")
