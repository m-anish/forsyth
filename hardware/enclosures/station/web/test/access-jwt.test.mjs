// Checks the API's Cloudflare Access token verification with self-made keys.
// Run: node test/access-jwt.test.mjs
import { onRequest } from "../functions/api/[[path]].js";

const team = "forsyth.cloudflareaccess.com", aud = "test-aud-123";
const b64u = buf => Buffer.from(buf).toString("base64url");
const { publicKey, privateKey } = await crypto.subtle.generateKey(
  { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
  true, ["sign", "verify"]);
const other = await crypto.subtle.generateKey(
  { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
  true, ["sign", "verify"]);
const jwk = { ...(await crypto.subtle.exportKey("jwk", publicKey)), kid: "k1", alg: "RS256" };
globalThis.fetch = async url => {
  if (String(url) === `https://${team}/cdn-cgi/access/certs`) return new Response(JSON.stringify({ keys: [jwk] }));
  throw new Error("unexpected fetch " + url);
};
async function token(claims, { key = privateKey, alg = "RS256", kid = "k1" } = {}) {
  const now = Math.floor(Date.now() / 1000);
  const head = b64u(JSON.stringify({ alg, kid, typ: "JWT" }));
  const body = b64u(JSON.stringify({ iss: `https://${team}`, aud: [aud], email: "Ann@Example.com", exp: now + 600, iat: now, ...claims }));
  const sig = alg === "none" ? "" : b64u(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(head + "." + body)));
  return head + "." + body + "." + sig;
}
const env = { DB: {}, ACCESS_TEAM_DOMAIN: team, ACCESS_AUD: aud };
async function call(headers, e = env) {
  const r = await onRequest({ request: new Request("https://build.forsyth.starstucklab.com/api/me", { headers }), env: e, params: { path: ["me"] } });
  return [r.status, r.status === 200 ? (await r.json()).email : null];
}
const now = Math.floor(Date.now() / 1000);
const cases = [
  ["valid token in header", { "cf-access-jwt-assertion": await token({}) }, 200],
  ["valid token in cookie", { cookie: "a=b; CF_Authorization=" + await token({}) }, 200],
  ["no token", {}, 401],
  ["wrong audience", { "cf-access-jwt-assertion": await token({ aud: ["someone-else"] }) }, 401],
  ["wrong issuer", { "cf-access-jwt-assertion": await token({ iss: "https://evil.cloudflareaccess.com" }) }, 401],
  ["expired", { "cf-access-jwt-assertion": await token({ exp: now - 10 }) }, 401],
  ["signed by another key", { "cf-access-jwt-assertion": await token({}, { key: other.privateKey }) }, 401],
  ["alg none", { "cf-access-jwt-assertion": await token({}, { alg: "none" }) }, 401],
  ["unknown key id", { "cf-access-jwt-assertion": await token({}, { kid: "nope" }) }, 401],
  ["tampered claims", { "cf-access-jwt-assertion": (await token({})).replace(/\.([^.]+)\./, (m, p) => "." + b64u(JSON.stringify({ ...JSON.parse(Buffer.from(p, "base64url")), email: "boss@example.com" })) + ".") }, 401],
  ["dev bypass ignored off localhost", { "x-dev-user": "x@example.com" }, 401],
];
let fails = 0;
for (const [name, headers, want] of cases) {
  const [got, email] = await call(headers, name.startsWith("dev") ? { ...env, DEV_USER_EMAIL: "dev@example.com" } : env);
  const ok = got === want && (want !== 200 || email === "ann@example.com");
  if (!ok) fails++;
  console.log((ok ? "ok   " : "FAIL ") + name + " -> " + got + (email ? " " + email : ""));
}
process.exit(fails ? 1 : 0);
