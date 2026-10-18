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
| Voices in the wire | for each undocumented code the meter sends (stored as `op_XX`) that is still unexplained and moves (not those decoded in [the study](archive/zytemp-channels.md), nor the constants sent only at power-up), its correlation with CO₂, temperature, elapsed time and (over ≥ 7 days) the Moon; the strongest one picks its spirit |
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
(Standish), referred to the equinox of date by the general precession, as
the tropical zodiac counts; Mercury's stations land within a day of the
published dates, and the equinoxes within a quarter of an hour. The Moon
uses the mean synodic month. None of it means anything.

## Prophecies

Every finding also prophesies, in up to three lines, each computed from the
same window as its reading: what it **foretells**, what it **counsels**, and
what it **reveals**. Counsel that would open a window follows the haze, as
above. The findings that foretell a series are also seers in [the
council](prophecy.md), which puts each of them to the test.

| Finding | Foretold, and how | Counsel; revealed |
|---|---|---|
| Aura | the air keeps returning to the window's mean (climatology) | the complementary colour, opposite on Goethe's circle; the hour of the day its aura is brightest and dimmest |
| Lunar influence | the next full and new moons, and (over a week or more) the CO₂ under each, by regressing CO₂ on illumination | the phase to gather under; how many ppm the Moon moves the room for each hundredth of its face |
| Mercury | over six hours: yesterday's air at each hour while Mercury is direct, the last hours mirrored in time while retrograde, the mean of the two in his shadow | what to finish before the next station, or redo after it, by the ephemeris; the reading at this hour yesterday |
| Chakra residency | a Markov chain over the chakra bands, in hourly cells (ten-minute ones under 12 h): the likeliest band within the hour and six cells on | the band to cross to raise the kundalini; the chain's long-run occupancy, its karma |
| Natal chart | the Sun's next ingress, and when it reaches the air's rising degree (its solar return) | the ppm nearest the mean that, read as degrees, trines or sextiles the Sun; the rising sign's element and quality |
| Schumann alignment | the strongest rhythm (FFT of the detrended window) carried on from its last period's level: its next crest and trough | the period that would be in tune; the room's note, raised into hearing |
| Divine proportion | a golden spiral from the last two turning points of a zigzag (a turn needs a tenth of the window's range): each swing 1/φ of the one before, a Fibonacci retracement, rising φ times as long as it falls, so it comes to rest at the 38.2 % retracement | the spiral's next crest, to air the room at; how many swings until it moves less than 5 ppm |
| Life path number | tomorrow's personal day number: the date's digits added to the life path, reduced | that day's task; the next master-number day (11, 22 or 33) |
| Voices in the wire | the unexplained code whose moves the CO₂ repeats soonest after (correlation on one-minute cells, leads up to 30 minutes, \|r\| ≥ 0.6), and the CO₂ that implies, by regression | heed it; the most restless voice, by its range against its favourite number |
| I Ching | the hexagram it changes into, line by line: a line that moved over twice its usual hourly change turns, the others keep their course | the judgement of the hexagram it becomes; its nuclear hexagram, lines 2–4 under 3–5 |
| Sensor society | whom your CO₂ follows, at lags of a cell up to 3 h, and the CO₂ that implies, by regression on the leader that much earlier (the Sun and the Moon lead from any distance) | steer the leader, or heed it; the guest whose moves the most others follow |
| Household choir | the air resolves to its tonic: an exponential return to the window's mean, with a time constant of one beat (an eighth of the window) | what the worst guest inside must come to for the house to sing one mode brighter, by bisection; the CO₂'s first phrase in movable-do solfège |
| Souls present | the CO₂ balance carried forward: the air settles at C_out + N g / (Q V), with time constant 1/Q, if the souls stay | how many souls the room holds below 1000 ppm, or how many air changes the present ones need; each soul's CO₂ in grams an hour, against MacDougall's 21 |
| Birth certificates | each member's next critical day, when one of its cycles next crosses zero | each member's best day in the next 33, where its three cycles add up highest, for its chores; the best day for the meter and the purifier together |
| Celestial clock | the daily rhythm carried on (the 24-hour fit, from the level its line has reached): the next culmination and nadir | the next planetary hour of the planet in whose hours the CO₂ stands highest; each guest's ruling planet, by its mean z-score in each planet's hours, with Ptolemy's nature of the planet |
| Five elements | the region your door's PM2.5 repeats best, one to three hours later (\|r\| ≥ 0.5), and what that implies by regression; failing that, the region the excess element feeds | the region with the cleanest air; how often the generating cycle foretold which region thickens next (the one the haziest feeds, over two hours), against how often any region does |
| Winds | the haze settles toward the mean of what the wind now blowing brought before, at the e-folding time of its hour-to-hour autocorrelation | the wind to air the room under, if any brought clean air; the prevailing wind's trigram |
| Ward | the haze now at your door reaching the purifier after the ward's lag, cut by its strength | the fan speed it holds best at, from the hours at each speed; how many motes in a hundred get in |
| Horoscope | tomorrow's planetary day, Moon and Mercury | |

## Sources

Where each method comes from, and the real methods its arithmetic borrows.
The occult sources are cited for what their traditions say, not because it
is so.

- **The sky**: E. M. Standish and J. G. Williams, [Approximate Positions of
  the Planets](https://ssd.jpl.nasa.gov/planets/approx_pos.html), JPL Solar
  System Dynamics (Table 1, valid 1800–2050 AD), referred to the equinox of
  date by the general precession of J. H. Lieske et al., Astronomy and
  Astrophysics 58: 1–16 (1977); the mean synodic month, 29.530588853 days:
  J. Meeus, *Astronomical Algorithms* (Willmann-Bell, 1991), ch. 47.
- **Aura**: C. W. Leadbeater, [*Man Visible and
  Invisible*](https://archive.org/details/dli.ministry.16766) (Theosophical
  Publishing Society, 1902), whose frontispiece is the "Signification of the
  Colours". The complement: J. W. von Goethe, [*Theory of
  Colours*](https://www.gutenberg.org/ebooks/50572), tr. C. L. Eastlake
  (1840), §50: "yellow demands purple; orange, blue; red, green". Foreseeing
  by the mean: the mean method of [Hyndman and Athanasopoulos
  (2021)](https://otexts.com/fpp3/simple-methods.html).
- **Lunar influence**: against the lunar effect, J. Rotton and I. W. Kelly,
  "Much ado about the full moon: a meta-analysis of lunar-lunacy research",
  Psychological Bulletin 97(2): 286–306 (1985), doi:10.1037/0033-2909.97.2.286.
- **Mercury**: the shadow as astrologers draw it, [Café Astrology, "Mercury
  Retrograde"](https://cafeastrology.com/mercuryretrograde.html); yesterday's
  air is the seasonal naïve forecast of Hyndman and Athanasopoulos (2021).
- **Chakra residency**: Arthur Avalon (John Woodroffe), *The Serpent Power*
  (Luzac, 1919), ch. V, "The Centres or Lotuses" ([2nd ed., archive.org](https://archive.org/details/in.ernet.dli.2015.283748)).
  The chain: A. A. Markov's 1913 study of the letters of *Eugene Onegin*,
  translated in Science in Context 19(4): 591–600 (2006),
  doi:10.1017/S0269889706001074.
- **Natal chart**: Ptolemy, [*Tetrabiblos*](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Ptolemy/Tetrabiblos/1B*.html),
  tr. F. E. Robbins (Loeb, 1940), Book I: the aspects (I.13), the signs
  counted from the equinoxes (I.22), their triplicities; the solar return:
  W. Lilly, [*Christian Astrology*](https://archive.org/details/bim_early-english-books-1641-1700_christian-astrology-_lilly-william_1647)
  (1647), Book III, "Of Revolutions".
- **Schumann alignment**: W. O. Schumann, Zeitschrift für Naturforschung A
  7(2): 149–154 (1952), doi:10.1515/zna-1952-0202; M. Balser and C. A.
  Wagner, Nature 188: 638–641 (1960), doi:10.1038/188638a0, the first
  detailed spectra near 7.8 Hz. Carrying a rhythm on past the record is how
  tides have been predicted since W. Thomson's harmonic tide predicter,
  Minutes of Proceedings of the ICE 65: 2–25 (1881), doi:10.1680/imotp.1881.22262.
- **Divine proportion**: L. Pacioli, [*Divina proportione*](https://archive.org/details/divinaproportion00paci)
  (Venice, 1509). Against it: M. Livio, *The Golden Ratio* (Broadway, 2002),
  ch. 4, on the Parthenon; G. Markowsky, "Misconceptions about the Golden
  Ratio", College Mathematics Journal 23(1): 2–19 (1992), doi:10.2307/2686193;
  and C. Falbo, "The Golden Ratio: A Contrary Viewpoint", College Mathematics
  Journal 36(2): 123–134 (2005), doi:10.1080/07468342.2005.11922119, who
  measured nautilus shells. The retracements: A. J. Frost and R. R. Prechter,
  [*Elliott Wave Principle*](https://archive.org/details/elliottwaveprinc0000ajfr)
  (New Classics Library, 1978), ch. 4, "Ratio Analysis and Fibonacci Time
  Sequences".
- **Life path number**: the digits of a birth date added up are L. Dow
  Balliett's "birth number" ([*The Philosophy of Numbers*](https://archive.org/details/cu31924028928798),
  1908) and Juno Jordan's "Birth Force", with master numbers 11 and 22 and
  personal years, months and days (*Numerology: The Romance in Your Name*,
  DeVorss, 1965). The name "life path" and the master 33 came later.
- **Voices in the wire**: what the codes are, [the zyTemp
  study](archive/zytemp-channels.md); the dead heard in recordings: K.
  Raudive, *Breakthrough* (Colin Smythe, 1971), after F. Jürgenson, *Rösterna
  från rymden* (1964).
- **I Ching**: R. Wilhelm, tr. C. F. Baynes, *The I Ching or Book of Changes*
  (Bollingen Series XIX, 1950): the hexagrams' names, the coin oracle, and the
  moving lines, 6 and 9, that turn a hexagram into the one it becomes, which
  shows where the situation leads. The trigrams' compass points: the Shuo Kua,
  ch. 5, in J. Legge, [*The Yî King*](https://archive.org/details/in.gov.ignca.20915),
  Sacred Books of the East 16 (1882), Appendix V, p. 425.
- **Sensor society**: J. L. Moreno, [*Who Shall Survive?*](https://archive.org/details/whoshallsurviven00jlmo)
  (1934), the sociogram; a leader's past foretelling a follower: C. W. J.
  Granger, Econometrica 37(3): 424–438 (1969), doi:10.2307/1912791.
- **Household choir**: C. L. Krumhansl and E. J. Kessler, Psychological
  Review 89(4): 334–368 (1982), doi:10.1037/0033-295X.89.4.334, and
  Krumhansl, *Cognitive Foundations of Musical Pitch* (Oxford, 1990), ch. 4,
  the key-finding algorithm written with M. Schmuckler; the modes ranked from
  Lydian to Locrian: V. Persichetti, *Twentieth-Century Harmony* (Norton,
  1961); the twelve modes: H. Glarean, *Dodecachordon* (Basel, 1547), who set
  aside the mode now called Locrian; their ethos: Plato, [*Republic* III
  398e–399c](https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.01.0168:book=3:section=398e);
  the planets' songs, and the Earth's mi, fa, mi: J. Kepler, [*Harmonices
  Mundi*](https://archive.org/details/ioanniskepplerih00kepl) (1619), V.6.
  The return to the tonic is mean reversion, after G. E. Uhlenbeck and L. S.
  Ornstein, Physical Review 36: 823–841 (1930), doi:10.1103/PhysRev.36.823.
- **Souls present**: the CO₂ balance and the 0.0052 L/s an adult breathes out
  at 1.2 met (light seated work): ASTM D6245, *Standard Guide for Using Indoor
  Carbon Dioxide Concentrations to Evaluate Indoor Air Quality and
  Ventilation*; the rates by age, sex and activity: A. Persily and L. de
  Jonge, Indoor Air 27(5): 868–879 (2017), doi:10.1111/ina.12383 (at rest a
  man breathes out nearer 13 L/h); air changes from a decay: ASTM E741. The
  weight of the soul: D. MacDougall, [Journal of the American Society for
  Psychical Research 1(5): 237–244](https://archive.org/details/sim_journal-of-the-american-society-for-psychical-research_1907-05_1_5)
  (1907), whose first patient lost three-quarters of an ounce.
- **Birth certificates**: G. S. Thommen, *Is This Your Day?* (Crown, 1964),
  after Fliess, Swoboda and Teltscher's cycles and their critical days;
  against them, T. M. Hines, Psychological Reports 83(1): 19–64 (1998),
  doi:10.2466/pr0.1998.83.1.19. The Fire Horse of 1966: K. Kaku, Annals of
  Human Biology 2(2): 111–115 (1975), doi:10.1080/03014467500000651.
- **Celestial clock**: the planetary hours that name the days of the week:
  Cassius Dio, [*Roman History* 37.18–19](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Cassius_Dio/37*.html),
  who credits the Egyptians (the order is now called Chaldean); the houses:
  Lilly, *Christian Astrology*, Book I, ch. VII; the planets' natures:
  Ptolemy, *Tetrabiblos* I.4–5. The 24-hour fit is a cosinor, its peak the
  acrophase: G. Cornelissen, Theoretical Biology and Medical Modelling 11:
  16 (2014), doi:10.1186/1742-4682-11-16, after F. Halberg, Y. L. Tong and
  E. A. Johnson (1967), doi:10.1007/978-3-642-88394-1_2.
- **Five elements**: J. Needham, [*Science and Civilisation in China*](https://archive.org/details/bwb_S0-ASX-485_2),
  vol. 2 (Cambridge, 1956), §13(d): the generating and overcoming orders
  (pp. 255–256) and the table of correspondences (pp. 262–263).
- **Winds**: the Tower of the Winds, [Vitruvius I.6.4](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Vitruvius/1*.html),
  who gives the winds Latin names; the Greek names on the tower itself: J. V.
  Noble and D. J. de Solla Price, American Journal of Archaeology 72(4):
  345–355 (1968), doi:10.2307/503828. The haze each wind brings is a
  pollution rose, as in D. C. Carslaw and K. Ropkins, Environmental Modelling
  & Software 27–28: 52–61 (2012), doi:10.1016/j.envsoft.2011.09.008.
- **Ward**: Q. Chen and B. Zhao, "Review of relationship between indoor and
  outdoor particles", Atmospheric Environment 45(2): 275–288 (2011),
  doi:10.1016/j.atmosenv.2010.09.048.
- **The haze's limits**: the WHO [global air quality guidelines](https://www.who.int/publications/i/item/9789240034228)
  (2021): PM2.5 15 and PM10 45 µg/m³ over 24 hours; the US EPA's [24-hour
  PM2.5 standard](https://www.epa.gov/criteria-air-pollutants/naaqs-table),
  35 µg/m³.
- **Horoscope**: the newspaper sun-sign column, which grew from R. H.
  Naylor's horoscope for Princess Margaret in the Sunday Express of 24 August
  1930 into Britain's first regular astrology column.
