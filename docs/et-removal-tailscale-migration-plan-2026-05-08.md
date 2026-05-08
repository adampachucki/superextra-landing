# Migration plan — drop ET, mosh-only over Tailscale (2026-05-08)

## Goal

Replace the current dual-transport stack (ET on Mac + mosh on iPhone, public IPv4 with TCP-IAP fallback for v6-only networks) with a **single transport (mosh) over a single network (Tailscale)** for both clients. Reduce public attack surface in the process.

## Outcomes

- One transport (mosh) on both Mac and iPhone — same mental model, same diagnostics.
- One network plane (Tailscale) — VM not reachable from public internet for terminal traffic.
- ~150 lines of zshrc and 4 services/scripts gone (CVM_ET, IAP fallback, launchd watcher, vp proxy).
- GCP firewall closed for ET and (optionally) mosh/SSH on public IPs.
- Single doc section to maintain instead of three (ET, IAP fallback, vp proxy).

## Before vs after

### Before

```
Mac, v4-direct:   VS Code → ET (TCP 2022, public IP)      → bash → tmux → claude
Mac, v6-only:     VS Code → ET via lo0 alias + IAP TCP    → bash → tmux → claude
iPhone:           Moshi   → mosh (UDP 60000-61000, public) → bash → tmux → claude
codex-az v6 fix:  Mac codex → vp proxy (SOCKS5/HTTP CONNECT via VM SSH) → Azure
```

### After

```
Mac (any net):    VS Code → mosh (Tailscale)              → bash → tmux → claude
iPhone (any net): Moshi   → mosh (Tailscale)              → bash → tmux → claude
codex-az:         Mac codex → direct (or via Tailscale exit-node if v6-only) → Azure
```

---

## Phase status

| #   | Phase                                                | Status         |
| --- | ---------------------------------------------------- | -------------- |
| 0   | Tailscale on Mac + iPhone, ai-workstation Host block | ✅ done        |
| 1   | Trial mosh-via-tailnet                               | 🔄 in progress |
| 2   | Mac zshrc rewrite (replace CVM_ET, drop IAP)         | pending        |
| 3   | SSH config cleanup                                   | pending        |
| 4   | IAP fallback teardown (Mac + VM)                     | pending        |
| 5   | ET teardown (Mac + VM + GCP firewall rule)           | pending        |
| 6   | iPhone Moshi host config switch                      | pending        |
| 7   | GCP firewall tightening (security)                   | pending        |
| 8   | codex-az / Tailscale exit-node decision              | pending        |
| 9   | Doc rewrite + decision history                       | pending        |

Phases 2–5 are reversible at each gate (backups + git). Phase 7 is reversible (re-create firewall rules). Phase 0 already done; Phase 1 runs in parallel with daily use.

---

## Phase 1 — Trial mosh-via-tailnet (validation, no config changes)

**Goal:** prove mosh-via-tailnet is solid for daily use before tearing anything down.

**Steps:**

1. From any Mac terminal: `mosh adam@ai-workstation` (no flags).
2. Inside, run `x test-mosh-tailnet` — land in claude.
3. Use it for real work for at least a day.
4. Stress test: laptop sleep/wake, Wi-Fi flip, network change, mid-session app activity.

**Pass criteria:**

- mosh auto-resumes after every disconnect within ~5s.
- No noticeable input-latency or rendering artifacts compared to ET.
- claude+codex run without issues.

**If pass:** proceed to Phase 2.
**If fail:** investigate (likely MTU/MSS over Tailscale, mosh-server PATH, or env propagation). Don't proceed.

---

## Phase 2 — Mac `~/.zshrc` rewrite

**Goal:** make `x` / `c` use mosh-over-tailnet instead of ET. Drop IAP machinery.

**Backup first:**

```
cp ~/.zshrc ~/.zshrc.bak-pre-et-drop-2026-05-08
```

**Remove (target ~150 LOC):**

- Functions: `CVM_ET`, `_x_route`, `_x_iap_active`, `_x_iap_up`, `_x_iap_down`, `_x_iap_status`, `_x_alias_present`, `_x_listener_alive`, `_x_v4_direct`, `_x_sudo`, `vp` family
- Subcommand: `x iap [up|down|status]`
- `X` config map keys: `et_port`, `iap_instance`, `iap_zone`, `pidf`, `logf` (keep `vm_host`, `vm_repo`)
- `codex-az`'s `vp_up` fallback logic — codex-az becomes a thin alias

**Add (replacement helper, ~3 lines):**

```zsh
CVM_MOSH() { mosh adam@${X[vm_host]} -- bash -ic "$1"; }
```

**Updated `x()` skeleton (~30 lines vs current ~120):**

```zsh
x() {
  _x_title() { printf '\033]0;%s\007' "$1"; }
  case "$1" in
    l)  local name; name=$(_x_pick_remote "Join") || return
        x j "$name" ;;
    j)  [ -n "$2" ] && _x_title "$2" && CVM_MOSH "x j '$2'" || x l ;;
    k)  local name="$2"
        [ -z "$name" ] && { name=$(_x_pick_remote "Kill") || return; }
        ssh ai-workstation "bash -ic 'x k \"$name\"'" ;;
    K)  ssh ai-workstation "bash -ic 'x K'" ;;
    *)  if [ -n "$1" ]; then _x_title "$1" && CVM_MOSH "x '$1'"; else CVM_MOSH "x"; fi ;;
  esac
}
```

`c()` mirrors `x()` with `c` as the VM-side command.

**Validation gate:**

- `x test-zshrc-rewrite` — creates a session via mosh, lands in claude. ✓
- `xj test-zshrc-rewrite` — re-attaches. ✓
- `xl` — lists, picks, attaches. ✓
- `xk test-zshrc-rewrite` — kills. ✓
- `c test-codex` — codex session. ✓
- `xK` — wipes (only used to test, then leave alone). ✓

**Rollback:** `cp ~/.zshrc.bak-pre-et-drop-2026-05-08 ~/.zshrc && source ~/.zshrc`.

---

## Phase 3 — `~/.ssh/config` cleanup

**Drop:**

- `Match host superextra-vm,34.38.81.215 exec "..."` block + ProxyCommand line

**Keep:**

- `Host ai-workstation ...` block (added in Phase 0)
- `Host superextra-vm` block, optionally — but since we're not using it anywhere post-zshrc-rewrite, can drop too

**Validation:** `ssh ai-workstation 'echo ok'` works. `ssh superextra-vm` either works or fails depending on whether the block was kept.

---

## Phase 4 — IAP fallback teardown

**Files/services to remove:**

| Path                                                   | What it is             | How to remove                                                |
| ------------------------------------------------------ | ---------------------- | ------------------------------------------------------------ |
| `~/Library/LaunchAgents/co.pachucki.x-netchange.plist` | netchange watcher      | `launchctl bootout gui/$(id -u) co.pachucki.x-netchange; rm` |
| `~/bin/x-netchange.sh`                                 | watcher script         | `rm`                                                         |
| `/etc/sudoers.d/x-iap-lo0`                             | NOPASSWD for lo0 alias | `sudo rm`                                                    |
| `/tmp/x-iap.pid` / `/tmp/x-iap.log`                    | runtime state          | `rm` (if present)                                            |
| Any `gcloud compute start-iap-tunnel` running          | live tunnel            | `pkill -f start-iap-tunnel`                                  |
| Any `lo0` alias for 34.38.81.215                       | hijacked routing       | `sudo /sbin/ifconfig lo0 -alias 34.38.81.215` (if present)   |
| VM: `~/bin/codex-connect-proxy.py`                     | vp HTTP CONNECT proxy  | `ssh ai-workstation 'rm ~/bin/codex-connect-proxy.py'`       |

**Validation:**

- `launchctl list | grep x-netchange` — empty
- `pgrep -f start-iap-tunnel` — empty
- `ifconfig lo0 | grep 34.38.81.215` — empty
- `sudo -l` doesn't show the lo0 alias entries

---

## Phase 5 — ET teardown

**Mac:**

```
brew uninstall et
```

**VM:**

```
sudo systemctl disable --now et.service
sudo rm -rf /etc/systemd/system/et.service.d/
sudo rm /etc/et.cfg
# If installed via apt: sudo apt remove --purge eternalterminal
```

**GCP firewall:**

```
gcloud compute firewall-rules delete allow-et
```

**Validation:**

- `which et` on Mac — not found
- `systemctl status et.service` on VM — not loaded
- `nc -z -G 3 34.38.81.215 2022` from outside Tailscale — connection refused

---

## Phase 6 — iPhone Moshi host config switch

**Steps in Moshi app:**

1. Open Settings → existing host entry (likely pointing at `34.38.81.215`).
2. Change **HostName** to `ai-workstation.tailcb8df5.ts.net` (full FQDN — most reliable for MagicDNS resolution on iOS).
3. Leave User, SSH key, port unchanged.
4. Save and connect.

**Tailscale on iPhone must be on.** If `iphone171` shows offline in `tailscale status` from Mac, foreground the Tailscale app on the phone once.

**Validation:**

- Mosh picker shows tmux sessions on the VM (read via the tailnet path).
- Connect, run a session, drop to airplane mode → reconnect → mosh resumes.

---

## Phase 7 — GCP firewall tightening (security)

**The Tailscale CGNAT range is `100.64.0.0/10`.** This covers all tailnet members and is the source for restricting firewall rules to tailnet-only access.

**Rules to update or remove:**

| Rule                | Current                    | Target                           | Why                         |
| ------------------- | -------------------------- | -------------------------------- | --------------------------- |
| `allow-et`          | TCP 2022, 0.0.0.0/0        | DELETE                           | ET removed in Phase 5       |
| `allow-mosh`        | UDP 60000-61000, 0.0.0.0/0 | DELETE                           | mosh-via-tailnet only       |
| `default-allow-ssh` | TCP 22, 0.0.0.0/0          | source-restrict to 100.64.0.0/10 | SSH only via tailnet        |
| `allow-dev-server`  | TCP 5199, 0.0.0.0/0        | source-restrict to 100.64.0.0/10 | dev server only via tailnet |

**gcloud commands:**

```
gcloud compute firewall-rules delete allow-et
gcloud compute firewall-rules delete allow-mosh
gcloud compute firewall-rules update default-allow-ssh --source-ranges=100.64.0.0/10
gcloud compute firewall-rules update allow-dev-server --source-ranges=100.64.0.0/10
```

**Result:** VM has zero terminal-traffic public exposure. fail2ban becomes vestigial (no more bot probes). Bot-traffic-from-internet logs go silent.

**Break-glass consideration:** if Tailscale ever breaks (auth lapse, account issue, daemon crash), the VM becomes unreachable. Mitigations:

1. **GCP serial console access** — always available via gcloud. Survives any networking failure on the VM.
2. **Keep one path open**: optionally leave `default-allow-ssh` source-restricted to `100.64.0.0/10 + your home IP /32` as a redundancy. Trade: small extra public exposure.
3. **GCP IAP for SSH** — gcloud's IAP-tunnel-to-instance still works without firewall changes; works even if instance has no public IP. Useful as a last-resort recovery path.

Recommendation: tightest config (delete et + mosh, source-restrict ssh + dev-server to tailnet) + rely on GCP serial console / IAP-to-instance as the break-glass.

---

## Phase 8 — codex-az and Tailscale exit node

**Current:** codex-az on Mac uses `vp` proxy to reach Azure when Mac is on v6-only network. After Phase 4, vp is gone. Need a replacement for the v6-only-Mac codex-az flow.

**Options:**

1. **Do nothing.** Mac codex-az fails on v6-only nets. User manually uses `c` (codex on VM) instead. Simplest.

2. **Tailscale exit node.** Configure VM as exit node. Mac on v6-only routes v4 internet through VM.
   - VM: `sudo tailscale up --advertise-exit-node`
   - Tailscale admin console: approve VM as exit node
   - Mac: `tailscale up --exit-node=ai-workstation` when on v6-only (or use Tailscale's macOS UI toggle)
   - Cost: VM egress bandwidth.

**Recommendation:** Do nothing for now (option 1). If v6-only mac codex-az becomes a real pain point, revisit and add exit-node config. The 95% case (Mac on v4) just works.

---

## Phase 9 — Documentation

**File to rewrite:** `docs/vm-setup.md`

**Remove sections:**

- "EternalTerminal" subsection under Connection details
- "IPv6-only network fallback" entire section
- "vp proxy" mentions
- IAP-related operational guidance

**Add sections:**

- "Tailscale as the transport layer" — explains the security + simplification rationale
- Updated Architecture diagram (single mosh-on-tailnet flow)

**Decision history entry (top of section):**

```
### 2026-05-08 — Drop ET, mosh-only via Tailscale, close public ports

Replaced ET (Mac transport) with mosh, replaced public-IP routing with Tailscale on both
clients. Result: single transport, single network plane, zero public terminal exposure.

This reverses the 2026-05-06 finding that "Tailscale isn't load-bearing." With ET removed,
Tailscale becomes the v6-only fallback (since IAP is TCP-only and mosh runs on UDP). The
trade — Tailscale daemon always-on on Mac vs. ~150 LOC of IAP/lo0 hijacking machinery
deleted — was found acceptable on security grounds: GCP firewall now closed for ET (TCP
2022) and mosh (UDP 60000-61000), and SSH/dev-server source-restricted to the Tailscale
CGNAT range (100.64.0.0/10). No more bot brute-force noise.

Break-glass: GCP serial console + IAP-to-instance via gcloud both still available without
public ingress. fail2ban becomes vestigial; left in place as defensive depth.
```

---

## Risks and mitigations

| Risk                                                                      | Likelihood | Mitigation                                                                                                                                   |
| ------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Tailscale auth lapses (token expires, account issue) → no terminal access | Low        | GCP serial console + gcloud IAP-tunnel still available; can re-auth Tailscale via web from any browser                                       |
| Tailscale daemon crashes on Mac → no terminal access                      | Low        | Re-launch Tailscale; or revert to public-IP path temporarily (would need to re-open allow-mosh firewall rule, ~1min)                         |
| iPhone Tailscale fails → can't use Moshi remotely                         | Low        | Same as above; can't always toggle Tailscale on iPhone remotely though, would need to wait until back near Wi-Fi                             |
| Tailnet MagicDNS resolution issue                                         | Low        | Use `100.101.35.72` (tailnet IP) directly; bake into ssh_config                                                                              |
| Latency increase via Tailscale relay                                      | Low        | Tailscale typically uses direct WireGuard between peers; only falls back to DERP relay if peer-to-peer fails. Latency increase usually < 5ms |
| IAP teardown leaves orphan lo0 alias                                      | Low        | Phase 4 validation step explicitly checks `ifconfig lo0`                                                                                     |

## Estimated effort

| Phase | Time                               | Notes                     |
| ----- | ---------------------------------- | ------------------------- |
| 1     | ~1 day (passive)                   | trial during normal work  |
| 2     | 30 min                             | zshrc edit + validation   |
| 3     | 5 min                              | ssh_config edit           |
| 4     | 15 min                             | scripted teardown         |
| 5     | 15 min                             | brew + systemd + firewall |
| 6     | 5 min                              | one Moshi host edit       |
| 7     | 5 min                              | gcloud commands           |
| 8     | 0 (option 1) or 30 min (exit-node) | decision                  |
| 9     | 30 min                             | doc rewrite               |

**Total active time:** ~2 hours, spread across two sessions.

---

## Execute order recommendation

Day 1 (today):

- Phase 0 ✅
- Phase 1 — trial running

Day 2 (after phase 1 validation):

- Phase 2 — zshrc rewrite + validate
- Phase 3 — ssh_config trim + validate
- Phase 6 — iPhone Moshi switch (small, do early)

Day 2 or 3:

- Phase 4 — IAP teardown
- Phase 5 — ET teardown
- Phase 7 — firewall tightening
- Phase 8 — codex-az decision (likely "do nothing")
- Phase 9 — doc rewrite

Don't merge tear-down phases (4, 5, 7) into a single shot — do them separately so any single one can be rolled back independently.
