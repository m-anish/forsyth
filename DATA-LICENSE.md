# The readings are CC BY 4.0

Everything the Forsyth stations measure — temperature, humidity, pressure, wind,
rain, particulates, lightning, battery and radio telemetry, the camera frames and
the timelapses built from them — is published under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).

Use it for anything. Republish it, sell what you build on it, train something on
it, correct it, merge it with better data. The one condition is that you say
where it came from.

## Attribution

Anything that credits the source, links back, and names the licence. For example:

```
Weather data from the Forsyth mesh (Bir, Himachal Pradesh)
https://live.forsyth.starstucklab.com — CC BY 4.0
```

Under a chart, small print is plenty. In a dataset, a line in the README. Every
API response also carries it machine-readably, as an RFC 8288 link header:

```
Link: <https://creativecommons.org/licenses/by/4.0/>; rel="license"
```

## What this covers, and what it doesn't

| | licence |
|---|---|
| Readings, lightning events, telemetry, CSV exports | **CC BY 4.0** (this file) |
| Camera frames and timelapses | **CC BY 4.0** |
| Human weather reports | **CC BY 4.0** — locations are deliberately rounded to ~100 m before they are ever served |
| Forecast rows from `/forecast` | **not ours.** [Open-Meteo](https://open-meteo.com)'s model output, under Open-Meteo's terms |
| River reaches from `/stations/{slug}/river` | **not ours.** [Google Flood Hub](https://sites.research.google/floods/), also CC BY 4.0 — so you may reuse it, but the attribution you owe is Google's, not ours |
| Verification numbers from `/skill` | **CC BY 4.0** — bias and error computed here, from our own readings |
| Map tiles | whoever drew them; each is credited on the map |
| The code in this repository | [MIT](LICENSE) |

## An honest note about what this licence can and cannot do

In much of the world a raw measurement is a fact, and facts are not
copyrightable. Over a single reading this licence may have nothing to attach to;
over a whole database it may, under sui generis database rights, depending on
where you are. CC BY 4.0 covers both where both exist.

So read the attribution clause as what is being asked of you, not as a threat.
It is here so that a chart somewhere can be traced back to a hillside in
Himachal — not to generate correspondence.

## One thing that is not a licence condition

Do not present these as official observations. They come from homemade stations
on a hillside, maintained by one person, and a sensor can be wrong for a week
before anyone notices. Do not use them where being wrong matters — aviation, or
anything load-bearing. Each station's `/skill` endpoint reports honestly how far
off its forecasts have been; the sensors deserve the same scepticism.

Written for humans, with the traps spelled out, at
<https://live.forsyth.starstucklab.com/api>.
