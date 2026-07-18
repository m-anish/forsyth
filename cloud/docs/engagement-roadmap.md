# Engagement roadmap — the people half of the insight engine

Written 2026-07-18, companion to [insight-roadmap.md](insight-roadmap.md). That
document says what the machines will do; this one says why anyone will care,
contribute, and stay. Decisions below were settled with the project owner on
2026-07-18; the rest is proposal, revised as reality reports in.

## 1. The premise

The insight engine gets better with density: more stations, more human reports,
more forecast-vs-truth pairs. Density is a community outcome, not a hardware
purchase. So the engagement model is a reciprocity deal, stated plainly:

> **Share what your patch of sky is doing; get back what it's about to do.**

Data in, insight out. Money optional. This only works if the deal is honest —
which fixes our first principle:

**Everything public today stays public forever.** The live dashboard, station
data, CSV export, the map — none of it ever moves behind an account. Forsyth's
differentiator against every consumer weather cloud is that it is self-hosted
and open; paywalling the commons would spend the one thing we can't buy back.
Accounts gate *new, additional* things only.

## 2. The deal, in tiers

| Tier | Who | What they get |
|---|---|---|
| **Visitor** | anyone | Everything that exists today: live boards, station pages, forecasts, skill scores, map, CSV. Anonymous weather reports (rate-limited). |
| **Account** (free, always) | signed-up | Saved places, personalized banner, report attribution + streaks, alert subscriptions (in-app/web push), monthly "your valley" digest. |
| **Contributor** (earned, not bought) | hosts a station, or sustains corroborated reports | Advanced insight as it exists: corrected hyperlocal forecast (Phase D), priority/earlier alerts, full skill history, annual monsoon report credit, name on the station page. |

Contribution is the currency. A contributor who never pays a rupee outranks a
subscriber who never looks at the sky — because the deal is data for insight,
not money for insight.

**Money** enters exactly where delivery costs money, and nowhere else:
SMS/WhatsApp alert delivery at cost, a commercial API tier for businesses,
adopt-a-station sponsorships (a name on a station page, hardware at cost).
Research and individual data access stays free, forever. No paid tier is
promised or designed until the free loop demonstrably works.

## 3. Reports and reputation (Phase B mechanics)

- **Anonymous stays one tap.** mPING's decade of operation says friction kills
  reporting; its reports are anonymous and still operationally useful because
  they are cross-checked. Ours are QC'd against the nearest fresh station at
  insert (see insight-roadmap §3). Rate limiting by hashed client, not identity.
- **Accounts make reports count.** Attribution, streaks (CoCoRaHS-style),
  and a **trust score that is earned mechanically**: reporters whose reports
  keep getting corroborated by nearby sensors graduate to *trusted observer*.
  Trusted reports carry more weight in the QC engine and can trigger alerts
  on their own (a trusted "hailing now" is actionable; an anonymous one wants
  a second signal). The score is functional, not decorative — and therefore
  self-cleaning: gaming it requires being reliably right about the weather,
  which is the desired behavior.
- **Ask at the right moment.** Reports spike during events. When divergence or
  lightning fires near a subscriber, prompt: "The models didn't see this.
  What's the sky doing where you are?" A request for help at the moment
  helping matters is engagement no campaign can buy.
- **Anti-gaming guardrails:** no leaderboard weighting on raw volume — only
  corroboration rate and coverage matter; contradicted reports quietly decay
  the score; `contradicted` near a station is a signal to inspect, not punish
  (sometimes the reporter is right and the sensor is wrong — that's QC gold).

## 4. Identity and sign-in

Decided: **Google OAuth + self-serve email/password + GitHub**, in that order
of expected use. Google is one tap on nearly every phone in Himachal; email
keeps us dependency-free; GitHub speaks to the open-hardware crowd who might
build leaves. All three land on the existing scrypt/session-cookie plumbing
(`accounts.py`) — OAuth via a small OIDC client, no framework change.
**Deferred:** Apple (only becomes necessary if an iOS app ships),
Facebook (poor privacy optics for a trust-first project).

## 5. Channels and language

- **WhatsApp is the channel in rural India.** Not another app. Alert
  broadcasts, event prompts, and eventually report-by-WhatsApp matter more
  than any dashboard feature for reach beyond the tech-comfortable. Start with
  a manually-run broadcast list during monsoon events; automate only after the
  alert engine (insight-roadmap Phase C) exists.
- **Hindi first-class** in the report flow and alerts (Pahari greetings where
  charm helps). A one-thumb report dialog in Hindi does more for adoption
  than every badge combined.
- The PWA already installs; web push covers Android. SMS only as a paid
  cost-recovery channel later.

## 6. Cultural seeding — Himachal-specific constituencies

Generic growth playbooks fail here; these are the people who already care
about the sky, ordered roughly by how sharply weather costs them money:

1. **Orchardists** (apple, stone fruit): frost and hail are livelihood events.
   Frost alerts (already in the banner) and hail reports are the wedge. Reach
   via KVKs (Krishi Vigyan Kendra) and horticulture dept advisories.
2. **Bir-Billing paragliding community**: a world-class site nearby, weather-
   obsessed, internationally networked. Wind/gust pages and a launch-site
   station would seed both data and word-of-mouth.
3. **Schools**: a station at a school = a caretaker, a curriculum hook (Atal
   Tinkering Labs), and a generation of locals who know the mesh by name.
4. **Trek/tour operators and taxi unions**: route-relevant alerts.
5. **Panchayats + DDMA Kangra**: the community-EWS angle (ICIMOD's model —
   a known local observer with a channel — is the credibility template).
6. **HAM/SWL and maker communities**: leaf builders and coordinator hosts.

**Campaign artifacts:** shareable auto-generated cards ("my valley's month" —
a PNG of the station's weather story, contributor credited) for WhatsApp
status and social; an annual **Monsoon Report** crediting every named
contributor; "station keeper" identity for hosts (handbook, name on page).
Social badges are the *output* of contribution, never the goal.

## 7. Guardrails

- **Location privacy:** public report coordinates fuzzed (~100 m) — homes are
  sensitive; exact coords stored, never published. Station siting already goes
  through the owner.
- **Data license:** publish the archive under an explicit open license
  (CC-BY 4.0 proposed — attribution builds the brand; decide before the first
  external researcher asks, not after).
- **No dark patterns:** no engagement streak guilt, no notification spam —
  alerts fire on weather, digests monthly, everything unsubscribable in one tap.
- **Privacy page** (privacy.html) grows an accounts/reports section the same
  PR that ships accounts.

## 8. What to measure (so we argue with numbers)

North star: **weekly active contributors** (reporters + station hosts with
fresh data). Supporting: reports per weather event, corroboration rate,
alert open/ack rate, stations live, and — the honest one — whether `/skill`
improves where density grows. Vanity counts (signups, followers) reported
but never optimized.

## 9. Sequence

| Step | What | Tied to |
|---|---|---|
| E1 | Report flow ships anonymous-first (✅ 2026-07-18); self-serve accounts (email + Google, then GitHub); attribution + streaks | insight Phase B |
| E2 | Trusted-observer mechanics; event-moment prompts; WhatsApp broadcast list (manual) | insight Phase C |
| E3 | Digests, shareable cards, Monsoon Report v1; school + Bir outreach; Hindi report flow | after B stabilizes |
| E4 | Sponsorships, SMS/WhatsApp automation, commercial API — only if E1–E3 earn it | after Phase D |

Parallel: IMD API key **requested 2026-07-18** (owner) — an official-warnings
overlay lands in the parallel track of insight-roadmap.md when it arrives.
