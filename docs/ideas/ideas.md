Don't record universally constant channels

Calibrate the CO2 meter
Map the CO2 meter's altitude correction at 1000, 2000 and 3000 m (../archive/zytemp-channels.md)
Smooth `home_pressure` in time, to average out more of the METARs' whole-hPa rounding
Chart the outdoor pressure on the dashboard
Drop the stale CO2 frames the meter sends right after power-up

Update devices firmware

More data:
Bluetooth & WiFi devices
SP power & water
Laptop's camera and microphone

Use the Google Health data (../health.md): chart heart rate and sleep on the dashboard; take
`health_sleep` as a known occupant of the bedroom, to fit the night's air changes from the CO2
rise and test the Oracle's souls count; weight each soul's CO2 by heart rate; set bedroom CO2
against the night's awake minutes, HRV and resting heart rate over many nights, with the bedroom
temperature held apart. SpO2 should not follow CO2 at all, which makes it a negative control.

Keep the zyTemp next to the purifier for several days, so that a few of the eCO2 reference
resets are recorded (the 13-hour side-by-side run is in ../archive/blueair-eco2.md). Keep the
meter on the purifier's intake side (right side), not by the outlet, since the outlet air would
also affect the meter's temperature reading. Outdoor air carries heavy PM, so the usual check
(open a window and see CO2 fall to ~420) costs PM indoors. Use occupancy changes (empty room,
sleeping, guests) and cooking events instead, and keep any airing short with the purifier on
high.

Check the zyTemp's temperature against the outdoor stations, to tell which device carries the
0.9 °C left between it and the purifier with the fan off (../archive/blueair-temperature.md).
Put the laptop and meter outside late at night, in shade and away from walls warm from the day;
let it settle for an hour and record for one or two more. The `nea_temperature_*` stations
disagree by about 1.25 °C at night, but a balcony runs warmer than a station on grass, so a
reading clearly below them points at the zyTemp.

Test whether the VOC sensor responds at all: hold an open bottle of rubbing alcohol or hand
sanitizer near the intake for a minute, and expect a VOC/eCO2 spike within one or two 5-minute
uploads. Best done while VOC sits near zero, as it did after 2026-10-17 18:17.

Check which NEA region's outdoor PM2.5 best tracks the purifier's PM2.5 when windows are open.

Infer the AC state from the indoor temperature against the outdoor one (`nea_temperature_*`): a
room far below outdoor, or cooling faster than it would on its own, has the AC on. Check the
inference against a few hand-noted AC on/off times before relying on it.

Measure the living room's air changes properly: leave it empty for an hour and fit the CO2 decay
(the tracer-gas decay method), then compare with the Oracle's souls regression, which found 0.6
to 0.9 changes an hour on 2026-10-17 but fails when people come and go. A real figure would make
the souls count less of a guess, and needs no airing.

More pseudoscience, not tried yet: apparitions, as jumps over three standard deviations, logged as
ghost sightings; a log of the hexagram of every hour, to find the household's favourite, and to
score the I Ching's changing lines against the hours that followed.

The council of seers (../prophecy.md) is tried once, over the last sixth of the window. Rolling it
back over many past horizons would give each seer a steadier record, and weights that change less
from one refresh to the next.
