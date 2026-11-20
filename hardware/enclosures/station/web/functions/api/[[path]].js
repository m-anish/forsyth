// Assembly tracker API (Cloudflare Pages Function; D1 binding DB).
//
// Who is asking comes from Cloudflare Access: every request to /api must carry the
// signed token Access adds (Cf-Access-Jwt-Assertion header or CF_Authorization cookie).
// It is verified here against the team's public keys, so the API refuses anyone Access
// has not signed in, even on the pages.dev address that Access does not cover.
//
//   GET    /api/me                               -> {email}
//   GET    /api/builds                           -> {builds: [{id, name, owner, role, created}]}
//   POST   /api/builds            {name}         -> {id}                     (anyone signed in)
//   GET    /api/builds/:id                       -> {build, role, members, stamp, steps, parts, hw}
//   GET    /api/builds/:id/stamp                 -> {stamp}: changes whenever the build does
//   PATCH  /api/builds/:id        {name}         -> rename                   (owner)
//   DELETE /api/builds/:id                       -> delete with its records  (owner)
//   PUT    /api/builds/:id/:kind/:key  {...}     -> save one record          (owner, editor)
//   POST   /api/builds/:id/members {email, role} -> add or change a member  (owner)
//   DELETE /api/builds/:id/members/:email        -> remove (owner), or leave (yourself)
//
// Settings (Pages environment variables): ACCESS_TEAM_DOMAIN ("yourteam.cloudflareaccess.com"),
// ACCESS_AUD (the Access application's AUD tag; several may be given, comma separated).
// DEV_USER_EMAIL skips Access for local `wrangler pages dev` only: it is ignored unless the
// request comes from localhost.

const KINDS = new Set(["steps", "parts", "hw"]);
const ROLES = new Set(["editor", "viewer"]);
const SEG = /^[A-Za-z0-9_.~:@+-]{1,120}$/;
const EMAIL = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/;

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });

// ------------------------------------------------------------------ identity
let certCache = { at: 0, keys: null, team: "" };

function b64urlBytes(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function teamKeys(team) {
  if (certCache.keys && certCache.team === team && Date.now() - certCache.at < 3600_000) return certCache.keys;
  const r = await fetch(`https://${team}/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error("certs " + r.status);
  const { keys } = await r.json();
  certCache = { at: Date.now(), keys, team };
  return keys;
}

async function accessEmail(request, env) {
  const url = new URL(request.url);
  if (env.DEV_USER_EMAIL && (url.hostname === "localhost" || url.hostname === "127.0.0.1")) {
    const as = request.headers.get("x-dev-user");          // local testing of sharing only
    return (as && EMAIL.test(as) ? as : env.DEV_USER_EMAIL).toLowerCase();
  }
  const team = env.ACCESS_TEAM_DOMAIN, auds = (env.ACCESS_AUD || "").split(",").map(s => s.trim()).filter(Boolean);
  if (!team || !auds.length) return null;
  let token = request.headers.get("cf-access-jwt-assertion");
  if (!token) {
    const m = (request.headers.get("cookie") || "").match(/(?:^|;\s*)CF_Authorization=([^;]+)/);
    token = m && m[1];
  }
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  let header, payload;
  try {
    header = JSON.parse(new TextDecoder().decode(b64urlBytes(parts[0])));
    payload = JSON.parse(new TextDecoder().decode(b64urlBytes(parts[1])));
  } catch (e) { return null; }
  if (header.alg !== "RS256") return null;
  let keys;
  try { keys = await teamKeys(team); } catch (e) { return null; }
  const jwk = keys.find(k => k.kid === header.kid);
  if (!jwk) { certCache.keys = null; return null; }
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64urlBytes(parts[2]),
                                        new TextEncoder().encode(parts[0] + "." + parts[1]));
  if (!ok) return null;
  const now = Date.now() / 1000;
  if (typeof payload.exp !== "number" || payload.exp < now) return null;
  if (typeof payload.nbf === "number" && payload.nbf > now + 60) return null;
  if (payload.iss !== `https://${team}`) return null;
  const aud = [].concat(payload.aud || []);
  if (!aud.some(a => auds.includes(a))) return null;
  return typeof payload.email === "string" && EMAIL.test(payload.email) ? payload.email.toLowerCase() : null;
}

// ------------------------------------------------------------------ helpers
// A string that changes whenever anything a viewer sees in a build changes (a record saved,
// someone added or removed, a rename). Clients poll it cheaply and reload only on change.
async function stampOf(db, build) {
  const r = await db.prepare(
    "SELECT (SELECT MAX(updated) FROM items WHERE build = ?1) AS items, " +
    "(SELECT COUNT(*) || ':' || IFNULL(GROUP_CONCAT(email || '=' || role), '') FROM members WHERE build = ?1) AS members, " +
    "(SELECT name FROM builds WHERE id = ?1) AS name").bind(build).first();
  return [r.items || "", r.members || "", r.name || ""].join("|");
}

async function roleOf(db, build, email) {
  const r = await db.prepare("SELECT role FROM members WHERE build = ? AND email = ?").bind(build, email).first();
  return r ? r.role : null;
}

async function readJson(request, limit = 20000) {
  const text = await request.text();
  if (text.length > limit) throw new Error("too large");
  const body = JSON.parse(text || "{}");
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("not an object");
  return body;
}

const cleanName = s => String(s || "").replace(/\s+/g, " ").trim().slice(0, 80);
const newId = name => (cleanName(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "build")
  + "-" + crypto.randomUUID().slice(0, 8);

// ------------------------------------------------------------------ handler
export async function onRequest({ request, env, params }) {
  const db = env.DB;
  if (!db) return json({ error: "no database bound" }, 500);
  const me = await accessEmail(request, env);
  if (!me) return json({ error: "sign in required" }, 401);

  const path = [].concat(params.path || []).map(decodeURIComponent);
  const method = request.method;
  const now = new Date().toISOString();

  if (path[0] === "me" && path.length === 1 && method === "GET") return json({ email: me });
  if (path[0] !== "builds") return json({ error: "not found" }, 404);

  // /api/builds
  if (path.length === 1) {
    if (method === "GET") {
      const { results } = await db.prepare(
        "SELECT b.id, b.name, b.owner, b.created, m.role FROM builds b JOIN members m ON m.build = b.id " +
        "WHERE m.email = ? ORDER BY b.created").bind(me).all();
      return json({ builds: results });
    }
    if (method === "POST") {
      let body; try { body = await readJson(request); } catch (e) { return json({ error: "bad body" }, 400); }
      const name = cleanName(body.name) || "Station";
      const id = newId(name);
      await db.batch([
        db.prepare("INSERT INTO builds (id, name, owner, created) VALUES (?, ?, ?, ?)").bind(id, name, me, now),
        db.prepare("INSERT INTO members (build, email, role, added_by, added) VALUES (?, ?, 'owner', ?, ?)").bind(id, me, me, now),
      ]);
      return json({ id }, 201);
    }
    return json({ error: "method not allowed" }, 405);
  }

  const id = path[1];
  if (!SEG.test(id)) return json({ error: "bad build id" }, 400);
  const role = await roleOf(db, id, me);
  if (!role) return json({ error: "no such build, or it is not shared with you" }, 404);

  // /api/builds/:id
  if (path.length === 2) {
    if (method === "GET") {
      const build = await db.prepare("SELECT id, name, owner, created FROM builds WHERE id = ?").bind(id).first();
      const { results: members } = await db.prepare(
        "SELECT email, role, added_by, added FROM members WHERE build = ? ORDER BY role = 'owner' DESC, added").bind(id).all();
      const { results: rows } = await db.prepare(
        "SELECT kind, key, body, updated, updated_by FROM items WHERE build = ?").bind(id).all();
      const out = { build, role, members, stamp: await stampOf(db, id), steps: {}, parts: {}, hw: {} };
      for (const r of rows) {
        let b; try { b = JSON.parse(r.body); } catch (e) { continue; }
        out[r.kind][r.key] = { ...b, _updated: r.updated, _by: r.updated_by };
      }
      return json(out);
    }
    if (role !== "owner") return json({ error: "only the build's owner can do that" }, 403);
    if (method === "PATCH") {
      let body; try { body = await readJson(request); } catch (e) { return json({ error: "bad body" }, 400); }
      const name = cleanName(body.name);
      if (!name) return json({ error: "name required" }, 400);
      await db.prepare("UPDATE builds SET name = ? WHERE id = ?").bind(name, id).run();
      return json({ ok: true });
    }
    if (method === "DELETE") {
      await db.batch([
        db.prepare("DELETE FROM items WHERE build = ?").bind(id),
        db.prepare("DELETE FROM members WHERE build = ?").bind(id),
        db.prepare("DELETE FROM builds WHERE id = ?").bind(id),
      ]);
      return json({ ok: true });
    }
    return json({ error: "method not allowed" }, 405);
  }

  // /api/builds/:id/stamp: what changed, cheaply
  if (path.length === 3 && path[2] === "stamp" && method === "GET") return json({ stamp: await stampOf(db, id) });

  // /api/builds/:id/members[/:email]
  if (path[2] === "members") {
    if (path.length === 3 && method === "POST") {
      if (role !== "owner") return json({ error: "only the build's owner can share it" }, 403);
      let body; try { body = await readJson(request); } catch (e) { return json({ error: "bad body" }, 400); }
      const email = String(body.email || "").trim().toLowerCase();
      const r = String(body.role || "editor");
      if (!EMAIL.test(email)) return json({ error: "that is not an email address" }, 400);
      if (!ROLES.has(r)) return json({ error: "role must be editor or viewer" }, 400);
      if (email === me) return json({ error: "you already own this build" }, 400);
      await db.prepare(
        "INSERT INTO members (build, email, role, added_by, added) VALUES (?, ?, ?, ?, ?) " +
        "ON CONFLICT (build, email) DO UPDATE SET role = excluded.role").bind(id, email, r, me, now).run();
      return json({ ok: true });
    }
    if (path.length === 4 && method === "DELETE") {
      const email = path[3].toLowerCase();
      if (email !== me && role !== "owner") return json({ error: "only the owner can remove other people" }, 403);
      if (email === me && role === "owner") return json({ error: "the owner cannot leave; delete the build instead" }, 400);
      await db.prepare("DELETE FROM members WHERE build = ? AND email = ? AND role != 'owner'").bind(id, email).run();
      return json({ ok: true });
    }
    return json({ error: "not found" }, 404);
  }

  // /api/builds/:id/:kind/:key
  if (path.length === 4 && KINDS.has(path[2]) && SEG.test(path[3])) {
    if (method !== "PUT") return json({ error: "method not allowed" }, 405);
    if (role === "viewer") return json({ error: "you can view this build but not change it" }, 403);
    let body; try { body = await readJson(request); } catch (e) { return json({ error: "body must be a JSON object under 20 kB" }, 400); }
    delete body._updated; delete body._by;
    await db.prepare(
      "INSERT INTO items (build, kind, key, body, updated, updated_by) VALUES (?, ?, ?, ?, ?, ?) " +
      "ON CONFLICT (build, kind, key) DO UPDATE SET body = excluded.body, updated = excluded.updated, " +
      "updated_by = excluded.updated_by").bind(id, path[2], path[3], JSON.stringify(body), now, me).run();
    return json({ ok: true });
  }
  return json({ error: "not found" }, 404);
}
