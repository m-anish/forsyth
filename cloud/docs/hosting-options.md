# Hosting the Forsyth cloud — options & recommendation

**Written 2026-07-11.** Prices are list prices at time of writing; check before buying.
Sizing context: the whole docker stack (measured locally) idles around 600–700 MB RAM
and near-zero CPU; the only spiky loads are the nightly ffmpeg timelapse encode and
`docker compose build`. For 1–3 stations reporting every 1–5 minutes, **any 2 GB box is
comfortable; 1 GB works with a swapfile.** Disk: 25 GB lasts years at this data rate
(a year of 5-min readings for 3 stations is well under 1 GB; frames are pruned at 14
days; timelapses ~10–20 MB/day/camera).

## The field

| Option | Region for you | Spec that fits | ~Price/mo | Notes |
|---|---|---|---|---|
| **Hetzner Cloud CX22** | EU only (Falkenstein/Helsinki) | 2 vCPU / 4 GB / 40 GB | **€3.8–4.5 (~₹380–450)** | Best value in the industry, boring-reliable. EU round-trip (~140–180 ms from India) is irrelevant for 5-min sensor posts and fine for a dashboard |
| **DigitalOcean Basic** | **Bangalore (BLR1)** | 2 GB / 1 vCPU / 50 GB | $12 (~₹1,000) · 1 GB tier $6 | India region, slickest UI/docs, easy snapshots. The 1 GB tier + swap runs this stack fine |
| **Vultr** | **Mumbai** | 2 GB / 1 vCPU | $10–12 · 1 GB $5–6 | Comparable to DO, India POP, slightly cheaper |
| **Linode/Akamai** | **Mumbai** | 2 GB "Shared" | $12 · 1 GB $5 | Same class as DO/Vultr |
| **AWS Lightsail** | **Mumbai** | 2 GB | ~$10 (1 GB ~$5) | Fixed-price AWS; fine, but AWS console gravity for no benefit here |
| **Oracle Cloud Free Tier** | Mumbai/Hyderabad | Ampere ARM, up to 4 OCPU / 24 GB | **₹0** | Genuinely free forever and absurdly oversized — but signup/capacity friction is real, ARM (our images are multi-arch, so fine), and free-tier reclamation policies make it a hobbyist gamble. Fine as an experiment, not as the thing you rely on |
| A Pi at home + Cloudflare Tunnel | your wall | Pi 4/5 you may own | ₹0/mo | No rent, but you babysit power/uplink/SD-card mortality — the coordinator's availability shouldn't depend on the same roof as the stations |

## Recommendation for 1–3 stations

**Hetzner CX22** if the monthly bill matters most — it's a 4 GB box for the price of
everyone else's 1 GB, and EU latency is a non-issue for this workload.
**DigitalOcean 2 GB in Bangalore** if you prefer an Indian region, INR-friendly billing,
and the nicest snapshot/rebuild experience — worth the extra ~₹550/mo to some tastes.

Either way: **Ubuntu 24.04 LTS, the smallest 2 GB+ plan, one box.** No managed
database, no Kubernetes, no object storage yet — the compose file is the whole
architecture, and a snapshot is the whole DR plan (plus the nightly pg_dump).

## Setup, step by step (once you've picked)

1. **Buy the VPS** — Ubuntu 24.04, add your SSH public key at creation time, note the IP.
2. **Cloudflare DNS** (starstucklab.com zone): add `A` record `live.forsyth` → VPS IP,
   **grey cloud (DNS only)** to start — Caddy will fetch its own Let's Encrypt cert.
   (Orange-cloud later if you want CF caching/hiding: set SSL mode *Full (strict)*;
   MQTT 1883 can't ride the proxy — grey-cloud a `mqtt.forsyth` name for devices.)
3. **Provision + deploy** — either run [deploy.md](deploy.md) §1–3 yourself (~15 min), or:

### Giving Claude access to deploy for you

Nothing exotic — an SSH key on this Mac that the VPS trusts:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/forsyth_vps -N "" -C "forsyth-deploy"
cat ~/.ssh/forsyth_vps.pub   # paste into the VPS provider's SSH-key box at creation,
                             # or later: ssh-copy-id -i ~/.ssh/forsyth_vps user@<ip>
```

Then tell Claude the IP (and user). Everything in deploy.md — docker install, firewall,
clone, `.env`, `compose up`, MQTT credentials, smoke tests — can be driven over
`ssh -i ~/.ssh/forsyth_vps`. Cloudflare stays manual (one A record) unless you'd rather
hand over a **scoped API token** (My Profile → API Tokens → *Edit zone DNS*, limited to
`starstucklab.com`) — never the global key.

## Monthly cost picture (initial deploy)

| Item | ₹/mo |
|---|---|
| VPS (Hetzner CX22 ↔ DO 2 GB BLR) | ~400–1,000 |
| Cloudflare DNS | 0 (existing) |
| Let's Encrypt TLS via Caddy | 0 |
| Weather Underground | 0 |
| **Total** | **~₹400–1,000** |

Scaling note: this box is oversized for 3 stations by an order of magnitude; the same
setup carries dozens of leaves and several cameras before anything needs rethinking
(the first thing to move would be frames → object storage, ~₹100/mo, not soon).
