Does Blueair cloud only store a week of data? (On 2026-10-17 it returned 14 days of hourly means; longer not tried.)
Online DB
Add CLI endpoint

More data:
Google Health
Blutooth & WiFi devices
SP power & water
Laptop's camera an mirophone

Put the zyTemp next to the purifier to study Blueair's eCO2 (see ../blueair-eco2.md).
Put the meter on the purifier's intake side (right side), not by the outlet, since the outlet air
would also affect the meter's temperature reading. Run it for several days so that a few
reference resets are recorded. Outdoor air carries heavy PM, so the usual check (open a window
and see CO2 fall to ~420) costs PM indoors. Use occupancy changes (empty room, sleeping, guests)
and cooking events instead, and keep any airing short with the purifier on high. Note whether
cooking is on gas: it produces real CO2.

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

More pseudoscience, not tried yet: a tarot spread whose "future" card is drawn from an honest
one-hour CO2 forecast; each sensor's ruling planet, from its mean z-score in each planetary hour;
apparitions, as jumps over three standard deviations, logged as ghost sightings; a log of the
hexagram of every hour, to find the household's favourite.
