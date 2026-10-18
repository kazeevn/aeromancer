# The Prophecy

The methods of [the Oracle](oracle.md) and [the Tree of Life](kabbalah.md)
stay as they are, each reading the window in its own way and prophesying
from it. The Prophecy is the summary: it asks every method that can foresee
to foresee together, trusts each as far as it foresaw before, and reads one
prophecy from them all. The dashboard shows it above the Oracle, and
`python3 -m aeromancer prophecy --range 7d` prints it with the council's
tables. As everywhere here, the arithmetic is real; the emanations are not.

## The council of seers

Seventeen methods are seers: from the window's readings alone, each says
what a series will be at the middles of 24 cells over the next horizon. The
council foresees two series when they have readings: your breath (the
zyTemp's CO₂) and the haze at your door (NEA's PM2.5 for the home region).

| Seer | How it foresees | Breath | Haze |
|---|---|:-:|:-:|
| Aura | the window's mean (climatology) | ✓ | ✓ |
| Lunar influence | regression on the Moon's illumination, over a week or more | ✓ | ✓ |
| Mercury | yesterday at the same hour (seasonal naive) while direct; the past mirrored in time while retrograde; their mean in the shadow | ✓ | ✓ |
| Chakra residency | a Markov chain over the chakra bands, one cell a step | ✓ | |
| Schumann alignment | the strongest rhythm of the FFT, carried on | ✓ | ✓ |
| Divine proportion | the golden spiral of Fibonacci retracements | ✓ | ✓ |
| The I Ching | the changing lines: its usual hourly change, the way its line will turn, for an hour | ✓ | ✓ |
| The sensor society | regression on the guest it follows best, that many cells earlier | ✓ | ✓ |
| The household choir | exponential return to the mean (an AR(1)), a beat at a time | ✓ | ✓ |
| Souls present | the CO₂ mass balance, with the souls present and the fitted air changes | ✓ | |
| The celestial clock | the 24-hour fit (a cosinor) | ✓ | ✓ |
| Five elements | regression on the region the door follows, one to three hours earlier | | ✓ |
| The winds | toward the haze the present wind brought before | | ✓ |
| Tree of Life | a Markov chain over the sefirot | ✓ | |
| Gematria | the last hour's drift, until it spells the next word (drift, capped) | ✓ | ✓ |
| Atbash | the mirror of the newest reading | ✓ | ✓ |
| Week of creation | the mean at the same weekday and hour | ✓ | ✓ |

The horizon is a sixth of the shorter series' span in the window, at least
ten minutes and at most a day: 4 h for a full 24 h window, and a day once
both series have six days or more in it.

Each seer is asked twice: **then**, as if it were one horizon ago, shown only
the readings it would have had (the hindcast), and **now**, shown everything.
Its hindcast is scored against what happened over the last horizon (the
readings' mean in each cell, interpolated across a cell or two of gaps), by
its mean absolute and mean squared error, and against **the Skeptic**, who
expects nothing to change: the reading as it stood one horizon ago, all
along. A seer's skill is one minus the ratio of its squared error to the
Skeptic's over the same cells (Murphy 1988): above zero, it beat the Skeptic.

Seers that spoke then and speak now vote, each weighing the inverse of its
hindcast's mean squared error, normalized to one (Bates and Granger 1969): a
seer twice as far off weighs a quarter as much. The council's prophecy at
each moment is the weighted mean of what the voting seers say there, and
its spread is their weighted standard deviation. A seer silent then is
listed as untried and has no vote; a seer silent at some moments is left out
of them. No prophecy leaves what air can be: CO₂ from 400 to 5000 ppm, PM2.5
from 0 to 1000 µg/m³.

It is one trial over one horizon, so a seer can be lucky, and the weights
change as the window moves. The council's own error is flattering, since its
weights were set on the very hindcast it is scored on.

## The unified prophecy

Read from the two councils:

- **Foretold**: your breath at the horizon, when it crosses 1000 ppm (or,
  above it, falls back below 950), and its heaviest moment; the haze at the
  horizon, and its thinnest moment.
- **Counsel**, the one piece of advice here that is real. If the breath is,
  or will be, at 1000 ppm or more within the horizon: open a window now
  while the haze is under 35 µg/m³; otherwise air the room at the first
  moment the haze is foreseen under it, before the breath crosses 1000;
  otherwise keep the windows shut, thin the crowd and let the purifier run.
  Without a haze council it goes by the latest outdoor reading, as the
  Oracle does. If the breath stays under 1000 ppm, no airing is due, and if
  the haze is foreseen to return while it is thin now, close the window
  before it does.
- **Revealed**: the most and least trusted seers, and how far off they
  were; how the weight divides between the Oracle's seers and the Tree of
  Life's; how many seers foresee the breath rising, and, when all of them
  agree, the Sanhedrin's rule that a verdict nobody argued against acquits;
  whether the Skeptic came nearer than the council; and the air to come as
  a Hebrew numeral, with its nearest word.

### The spread

Three cards of the Major Arcana, dealt by the numbers rather than shuffled:
the past is what your breath did over the hindcast, the present its last
hour and the souls in it, and the future what the council foresees. The
first rule that fits deals the card:

| Card | When the breath, over the span |
|---|---|
| XVI The Tower | crosses 1000 ppm upward |
| XII The Hanged Man | stays at 1000 ppm or more throughout |
| XVII The Star | clears: from 800 ppm or more to below it, or by a fifth |
| XVIII The Moon | lies under a haze of 35 µg/m³ or more |
| XIX The Sun | stays below 600 ppm |
| VII The Chariot | rises by a fifth |
| X Wheel of Fortune | peaks inside the span, ranging over more than 15 % of its mean |
| XIV Temperance | ends within 5 % of where it began, never ranging over 10 % |
| VIII Strength | does anything else |

The present is The Lovers (VI) with 1.5 souls or more, The Hermit (IX) with
fewer than 0.3, The Devil (XV) at 1000 ppm or more, and otherwise dealt from
its last hour by the rules above. Each card shows its divinatory meaning, in
short, as Waite gives it.

## Sources

The occult methods' sources are with [the Oracle](oracle.md#sources) and
[the Tree of Life](kabbalah.md#sources). The council's:

- J. M. Bates and C. W. J. Granger, "The Combination of Forecasts",
  Operational Research Quarterly 20(4): 451–468 (1969),
  doi:10.1057/jors.1969.103: weighing forecasts by their past errors.
- A. H. Murphy, "Skill scores based on the mean square error and their
  relationships to the correlation coefficient", Monthly Weather Review
  116(12): 2417–2424 (1988), doi:10.1175/1520-0493(1988)116<2417:SSBOTM>2.0.CO;2;
  and, for persistence as the reference, "Climatology, persistence, and their
  linear combination as standards of reference in skill scores", Weather and
  Forecasting 7(4): 692–698 (1992), doi:10.1175/1520-0434(1992)007<0692:CPATLC>2.0.CO;2.
- R. J. Hyndman and G. Athanasopoulos, *Forecasting: Principles and
  Practice*, 3rd ed. (OTexts, 2021), [§5.2](https://otexts.com/fpp3/simple-methods.html):
  the mean (the Aura's), naïve (the Skeptic's), seasonal naïve (Mercury's,
  while direct) and drift (gematria's) methods.
- J. Smith and K. F. Wallis, "A Simple Explanation of the Forecast
  Combination Puzzle", Oxford Bulletin of Economics and Statistics 71(3):
  331–355 (2009), doi:10.1111/j.1468-0084.2008.00541.x: why weights set on so
  short a record may do no better than equal ones.
- A Sanhedrin's unanimous verdict to convict acquits: Babylonian Talmud,
  [Sanhedrin 17a](https://www.sefaria.org/Sanhedrin.17a.20).
- A. E. Waite, *The Pictorial Key to the Tarot* (Rider, 1910), Part III, the
  Greater Arcana's divinatory meanings ([Wikisource](https://en.wikisource.org/wiki/The_Pictorial_Key_to_the_Tarot/Part_3)).
