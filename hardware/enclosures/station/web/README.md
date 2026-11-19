# build.forsyth.starstucklab.com

The public assembly guide and the signed-in build tracker for the station kit, on
Cloudflare Pages (project `forsyth-build`) with a D1 database (`forsyth-build`).

| Path | What | Who |
|---|---|---|
| `/` | landing page | everyone |
| `/assembly`, `/*.pdf`, `/assembly/*.png` | the guide, its PDFs and pictures | everyone |
| `/app/` | the tracker (`docs/assembly-app.html`) | signed in through Cloudflare Access |
| `/api/*` | the tracker's API (`functions/api/[[path]].js`) | signed in; verified again in the Function |

Everything served comes from `../docs`, which `../build.sh` regenerates from the model.

## People and builds

Cloudflare Access signs people in with their email (a one-time code). The API checks the
token Access adds to every request (signature against the team's keys, audience, issuer,
expiry), so it refuses anyone not signed in, even on the `pages.dev` address that Access
does not cover. Each build has an owner, who can share it from the tracker's Team tab with
editors (tick steps, record measurements) and viewers (look only). Every saved record keeps
who saved it and when. Tables: `schema.sql`.

## Deploy

    ../build.sh            # parts, guide, app, PDFs
    ./deploy.sh            # assemble dist/ and publish it

`./deploy.sh --local` serves the same site on http://localhost:8788 with a local database,
signed in as `$DEV_USER_EMAIL` (default you@example.com); an `X-Dev-User` header picks another
person for testing sharing. Neither works anywhere but localhost.

`node test/access-jwt.test.mjs` checks the token verification (valid, expired, forged,
wrong audience or issuer, `alg: none`, tampered claims).

## One-time setup in the Cloudflare dashboard

Done by hand because wrangler's login cannot manage Zero Trust or DNS. All four steps were
done on 2026-11-19 (team `damp-frog-65f7`); they are here for rebuilding it elsewhere.

The DNS page flags the `build.forsyth` CNAME as not covered by a certificate (the zone's
universal certificate covers one level only). Ignore it: Pages issues and renews its own
certificate for each custom domain, and this one serves a valid one.

1. **Custom domain.** Workers & Pages, `forsyth-build`, Custom domains, Set up a custom
   domain: `build.forsyth.starstucklab.com`. Cloudflare adds the CNAME itself when the
   `starstucklab.com` zone is in the same account.
2. **One-time PIN login.** Zero Trust, Settings, Authentication, Login methods: make sure
   "One-time PIN" is on (Google can be added too).
3. **Access application.** Zero Trust, Access, Applications, Add an application,
   Self-hosted. Name `Forsyth build tracker`. Public hostnames: domain
   `build.forsyth.starstucklab.com`, path `app`; add a second hostname, same domain, path
   `api`. Policy: name `Anyone with an email`, action Allow, Include `Everyone`. Session
   duration as you like (a week is comfortable on a phone).
4. **Tell the API about it.** From the application's Overview tab copy the
   **Application Audience (AUD) Tag**, and from Settings, Custom pages (or the login URL) the
   **team domain** (`<team>.cloudflareaccess.com`). Put both in `wrangler.toml` under `[vars]`
   as `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD`, and run `./deploy.sh`.

Until step 4 the API answers every request with 401, which is the safe failure.
