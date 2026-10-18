# The dashboard

Live CO₂ with a status (fresh < 800 ≤ stuffy < 1200 ≤ ventilate < 2000 ≤
leave the room), temperature, humidity on meters that have it, the
purifier's filter ([health](blueair.md#filter-health) from the last decay
test, when it will be due, and the app's own timer), and two charts
of stacked panels on one time axis, one unit per panel: Air (CO₂ from the
meter, particles with NEA's outdoor PM2.5 shaded behind them, VOC, the
purifier's pollution index) and Climate (both temperatures, humidity). The
meter is drawn in blue with per-bucket min–max bands, the purifier in orange,
NEA in green. Mercury retrograde periods and full/new moons are marked on the
time axis, and so are the devices' moves ([placements](recording.md#where-the-devices-are)).
Hover or use the arrow keys on a chart to read every value at that moment.

The purifier's CO₂ is not charted: it is an estimate from its VOC sensor
that doesn't follow real CO₂ ([study](archive/blueair-eco2.md)).

Below the charts, a Filter card shows how the filter's tile was worked out:
the last decay test, both forecasts with their ranges, and the app's timer.
Then the dashboard reads your air through [the Oracle](oracle.md)
and [the Tree of Life](kabbalah.md). The Tree of Life's heading links to
itself, `#tree-of-life`, and each of the Oracle's cards has its own `#omen-…`.

The dashboard refreshes every 15 s while its tab is visible. Hosted, it
opens only through a share link, and says so when the link has expired
([cloud.md](cloud.md)).
