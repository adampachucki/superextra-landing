# agent.superextra.ai — Subdomain Options

## Current Setup

- `superextra.ai` → Firebase Hosting (site: `superextra-site`) — main marketing page, separate repo
- `landing.superextra.ai` → Firebase Hosting (site: `superextra-landing`) — this repo
- Cloud Functions handle `/api/*` routes (agent proxy, intake, TTS, etc.)
- Cloud Run (`superextra-agent`) runs the ADK agent — SSE stream called directly at `agentstream-*.run.app`
- Firebase project: `superextra-site`
- Agent UI currently at `landing.superextra.ai/agent` and `landing.superextra.ai/agent/chat`

---

## Options

### Option 1: Firebase Hosting Multi-site (Recommended)

Firebase Hosting supports multiple sites under one project. Add a second site (e.g. `superextra-agent-ui`), connect `agent.superextra.ai` as its custom domain, and deploy the agent UI there.

- Cloud Functions are shared across the project — API routes work without duplication
- Firebase handles SSL automatically
- Two separate deploy targets in `firebase.json` (one per site)
- Can be the same SvelteKit app with different entry routes, or a separate lightweight app

**Pros:** Simplest path, stays in Firebase, free SSL, shared functions, minimal infra change
**Cons:** Two build/deploy targets to manage (though the GH Actions workflow handles this easily)

### Option 2: Cloud Run domain mapping

Map `agent.superextra.ai` directly to a new Cloud Run service that serves the agent UI (static files + API proxy).

**Pros:** Full control, single service for UI + API, no Firebase dependency for the agent
**Cons:** Serving static assets from Cloud Run is less optimal (no CDN), you manage SSL via Cloud Run's managed certs, more moving parts

### Option 3: Google Cloud Load Balancer with host-based routing

Set up a Global HTTPS LB that routes by hostname:

- `superextra.ai` → Firebase Hosting backend
- `agent.superextra.ai` → Cloud Run service

**Pros:** Most flexible, clean separation, easy to add more subdomains later
**Cons:** ~$18/mo for the LB, most complex to set up, overkill for two routes

### Option 4: Cloudflare as reverse proxy

Move DNS to Cloudflare, use Workers or Page Rules to route `agent.superextra.ai` to the Cloud Run backend.

**Pros:** Edge caching, DDoS protection, flexible routing rules
**Cons:** Additional service dependency, need to move DNS management, adds a layer

---

## Recommendation: Option 1

Firebase Multi-site is the clear winner. The project is already on Firebase, it requires the least infrastructure change, and it gives a standalone `agent.superextra.ai` subdomain with its own content while sharing the same Cloud Functions backend.

### Implementation steps

1. Add a second hosting site in Firebase console (or via CLI)
2. Update `firebase.json` with a second hosting target
3. Add `agent.superextra.ai` as a custom domain on the new site in Firebase console
4. Set up a DNS CNAME record for `agent.superextra.ai`
5. Update the deploy workflow to deploy both sites

### Notes

- The frontend SSE stream already hits Cloud Run directly (`agentstream-*.run.app`), so that doesn't need to change
- Non-streaming API calls (`/api/agent/check`, etc.) would either stay as Cloud Function rewrites on the new site or also switch to direct Cloud Run calls
- `cloudfunctions.net` GFE proxy kills SSE streams — this is already worked around by calling the Cloud Run `run.app` URL directly for streaming
