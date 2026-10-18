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
Then comes [the Prophecy](prophecy.md): a tarot spread, the unified prophecy,
and the council of seers, as a chart of what each foresaw before now and
foresees after it, and a table of how far off each was and how much it is
trusted (hover a seer's row to light up its lines). Below it the dashboard
reads your air through [the Oracle](oracle.md) and [the Tree of
Life](kabbalah.md), each card ending in what its method foretells, counsels
and reveals. The Prophecy's and the Tree of Life's headings link to
themselves, `#prophecy` and `#tree-of-life`, and every card of the Oracle and
the Tree of Life has its own `#omen-…`; the omens under the page header start
with the prophecy's headline.

The dashboard refreshes every 15 s while its tab is visible. Hosted, it
opens only through a share link, and says so when the link has expired
([cloud.md](cloud.md)).
