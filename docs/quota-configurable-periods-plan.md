# Plan: configurable `{scope, period, limit}` usage quotas

## Goal

Replace the hardcoded daily research/continuation caps with a fully
config-driven model where each quota is a triple — **scope** (where the
counter lives), **period** (when it resets), **limit** (the number). One
mechanism expresses daily, weekly, monthly, yearly, lifetime, and
per-research models; switching between them is a `config/limits` edit in
the Firebase Console (no redeploy, instant — the gate reads config each
gated turn).

Owner decisions locked:

1. `week` = ISO calendar week (resets Monday).
2. `research` quota is **always account-scoped** (a per-session research
   limit is meaningless — ≤1 research per chat). Only `continue` scope is
   configurable.
3. `limitOverrides` overrides the **number only**, not period/scope.

## The two axes

- **scope**: `account` (one counter per user) | `research` (one counter
  per chat; a chat ≈ one research since the router runs `research_pipeline`
  at most once per chat). Research is hardcoded `account`.
- **period**: `day | week | month | year | ever`. Implemented as a
  **period key** string; the counter resets when the stored key != the
  current key.

```
period -> key(now)
  day   -> "2026-05-28"     (%Y-%m-%d)
  week  -> "2026-W22"       (%G-W%V, ISO year-week)
  month -> "2026-05"        (%Y-%m)
  year  -> "2026"           (%Y)
  ever  -> "ever"           (constant; never resets)
unknown -> fall back to "day" (safe: frequent reset, still bounded)
```

This is the _same_ reset logic the gate has today — it already does
`used = count if storedDate == today else 0`. We swap the hardcoded
`today` for `periodKey(period)`.

## Config schema (`config/limits`)

```jsonc
{
	"free": {
		"research": { "period": "day", "limit": 1 }, // scope implicit = account
		"continue": { "scope": "account", "period": "day", "limit": 5 }
	},
	"paid": {
		"research": { "period": "day", "limit": 50 },
		"continue": { "scope": "account", "period": "day", "limit": 100 }
	}
}
```

We ship with these **daily-equivalent** values so behavior is unchanged on
cutover. The owner flips to e.g. a free lifetime trial purely in the
Console:

```jsonc
"free": {
  "research": { "period": "ever",     "limit": 3 },
  "continue": { "scope": "research",  "period": "ever", "limit": 5 }
}
```

Validation (mirrors current `_sanitize_limit` discipline). Bad config is
**fail-generous and logged loudly** — NOT silently "safe" (Codex flagged
this): a typo in `period` ("everr") falls back to the per-plan default
period, which for free is `day`, i.e. a _resetting_ quota more generous
than the intended lifetime cap. That won't lock users out, but it under-
enforces against the operator's intent, so each substitution is logged so
the operator notices and fixes the doc:

- `period` not in {day,week,month,year,ever} -> per-plan default period (logged).
- `scope` (continue only) not in {account,research} -> default scope (logged).
- `limit` not a non-negative int -> per-plan default limit (logged).
- Whole doc missing -> code defaults (daily model above).

## Data model

User doc (`users/{uid}`):

```
researchCount, researchPeriodKey          // research, always account-scoped
continueCount, continuePeriodKey          // continue when scope=account
limitOverrides: { research?: int, continue?: int } | null   // number-only overrides
plan, email, displayName, ...             // unchanged
```

Session doc (`sessions/{sid}`), only when continue scope=research:

```
continueCount, continuePeriodKey          // this chat's continuation budget
```

Field renames from today (`researchRunsToday`/`lastResearchDateUtc`,
`continueRunsToday`/`lastContinueDateUtc`) -> the `*Count`/`*PeriodKey`
names. **No migration:** renamed fields start fresh (old ones ignored);
worst case is a one-time bonus allotment for users mid-period at cutover.

**Override-key rename.** `limitOverrides` moves from period-specific keys
(`researchPerDay`/`continuePerDay`) to `{ research, continue }` (the limit
is now period-agnostic). Live-data check (2026-05-28): exactly one user
doc carries a non-null `limitOverrides`, and it's on the _pre-rewrite_
schema (`{turnsPerChat:10, chatsPerDay:5}`) — already inert under today's
code. So the rename breaks no currently-functional override. **Owner
action:** that user's elevated-limit intent is already lost; re-grant
under the new keys if still wanted.

## Gate rewrite (`agent/superextra_agent/quota_gate.py`)

Unified gate, parameterized per quota. **One transaction** does the whole
thing — read the user doc (plan + override), resolve the spec, read the
counter doc, check, and write — so there's no plan/limit TOCTOU (revised
per Codex review; the earlier non-txn-read variant left a race where a
request could reserve against a stale plan/limit).

```
async def gate(callback_context):
    quota_uid = state.get("quotaUid") or callback_context.user_id
    if not quota_uid: return None
    try:
        fs       = client()
        config   = read config/limits                # global limits structure (non-txn ok)
        user_ref = users/{quota_uid}
        sid      = state.get("firestoreSid")
        reserved, plan = txn_reserve(fs.transaction(), user_ref, sid, config, quota_name, now)
    except Exception:
        log.exception(...); return None              # fail-generous (fairness, not security)
    if reserved: return None
    reply = block_message(plan, spec.period)         # period-aware wording
    state[QUOTA_BLOCK_REPLY_KEY] = reply
    return types.Content(role="model", parts=[types.Part(text=reply)])

def _reserve(txn, user_ref, sid, config, quota, now):           # @firestore.transactional
    user_snap = user_ref.get(transaction=txn)                   # READ 1 (plan + override)
    user_data = user_snap.to_dict() if user_snap.exists else None
    plan = _plan(user_data)
    spec = resolve_spec(config[plan], quota, user_data)         # {scope, period, limit}
    if quota == "continue" and spec.scope == "research" and sid:
        counter_ref  = sessions/{sid}/quota/continue            # subdoc, READ 2
        counter_snap = counter_ref.get(transaction=txn)
        counter_data = counter_snap.to_dict() if counter_snap.exists else None
    else:                                                       # account scope (or missing sid)
        counter_ref, counter_data, counter_snap = user_ref, user_data, user_snap
    key  = period_key(spec.period, now)
    used = counter_data.get(count_field, 0) if (counter_data or {}).get(period_field) == key else 0
    if used >= spec.limit:
        return (False, plan)
    update = { period_field: key, count_field: used + 1, "updatedAt": SERVER_TIMESTAMP }
    txn.update(counter_ref, update) if counter_snap.exists else txn.set(counter_ref, {...})
    return (True, plan)
```

Notes:

- All reads precede all writes (Firestore requirement): user doc first,
  then the session subdoc if research-scoped, then the single write. The
  installed client retries `Aborted` commits up to 5× under contention.
- For `account` scope the counter doc _is_ the user doc already read — no
  second read.
- `_make_gate(quota="research", count_field="researchCount",
period_field="researchPeriodKey", block_message=…)` and the same for
  continue. Factory stays thin (two callers, no duplication).

**Per-research counter lives in a subdoc** `sessions/{sid}/quota/continue`,
NOT on `sessions/{sid}` itself (revised per Codex). The session doc is the
busiest doc in a run (claim, status, heartbeat, lastEventAt, terminal) and
the browser holds a live listener on it — writing a counter there would add
contention and spurious client re-renders. A `quota` subcollection has no
match in `firestore.rules`, so it's denied to clients by default (server
clients bypass via IAM) and isn't in any client listener path.

Block wording is **period-aware** via a `_reset_phrase(period)` helper:
`day→"tomorrow"`, `week→"next week"`, `month→"next month"`, `year→"next
year"`, `ever→""` (e.g. "Research limit reached on the free plan. Try again
{phrase}." / for `ever`: "You've used your free research allowance.").

## Firestore rules / Cloud Function

- `sessions/{sid}` stays server-only-write; the engine's `firestore.Client`
  (service account) bypasses rules, same as the existing
  `FirestoreProgressPlugin` writes. No rule change for the new session
  field beyond the existing `write: if false`.
- `functions/index.js` lazy-provision keeps `limitOverrides: null`; no
  function changes — quota stays entirely agent-side.
- Update the live `config/limits` doc to the new nested schema
  (daily-equivalent values) as a deploy step.

## Tests (`agent/tests/test_quota_gate.py`)

- `_period_key`: day/week/month/year/ever, an ISO-week boundary
  (e.g. Sun->Mon), unknown->day.
- `_resolve_spec`: defaults; valid override (number); bad period->default;
  bad scope->default; research scope forced to account; whole-doc-missing.
- `_check_and_reserve`: under/at limit; period rollover (stored key !=
  current); lazy provision; counters independent.
- Gate e2e: research (account); continue account; continue research
  (asserts the **session** doc is the counter target); block messages
  (free vs paid); quotaUid precedence; fail-open; missing firestoreSid ->
  account fallback.

## Resolved after Codex review

1. **Period-aware block wording** — YES, `_reset_phrase(period)` helper.
2. **`ever` resettability** — constant `ever` (versioning is speculative; a
   one-off script can reset lifetime counters if ever needed).
3. **Cutover bonus** — accept the one-time fresh allotment; no migration.
4. **Per-research counter location** — `sessions/{sid}/quota/continue`
   subdoc, NOT the session doc (avoids contention + client-listener noise).
5. **TOCTOU** — eliminated by doing plan/limit + counter in one transaction.
6. **Bad-config fallback** — fail-generous + logged, not silent.

## Deploy order

1. Ship engine code (new fields + gates) via `redeploy_engine.py`.
2. Replace `config/limits` with the new nested schema (daily-equivalent
   values, so behavior is unchanged until the owner edits it).
3. Old counter/override fields on existing docs are ignored; no migration.
4. Optionally re-grant the one stale override under the new keys.

```

```
