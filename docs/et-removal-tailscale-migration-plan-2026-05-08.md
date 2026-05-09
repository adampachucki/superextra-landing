# Migration plan v3 — mosh over Tailscale only (2026-05-08, executable)

## Goal

Single terminal path: mosh over Tailscale to `ai-workstation`. Delete ET, IAP fallback, `vp` proxy, fail2ban, public ingress for terminal/dev traffic.

## Final firewall state

After this migration, GCP firewall on the `default` network has:

- `default-allow-icmp` — kept
- `default-allow-internal` — kept (intra-VPC)
- `allow-tailscale-direct` — **added** (UDP 41641 ingress for direct WireGuard P2P)
- everything else — deleted

Recovery: GCP serial console.

## Mental model

Tailnet traffic between Mac/iPhone and the VM is encapsulated in Tailscale's transport:

- **Direct path (preferred):** WireGuard over UDP 41641. Both ends learn each other's public IPs via Tailscale's coordination server, then NAT-punch a direct tunnel. GCP firewall must allow this UDP ingress for stable direct connections.
- **Relay fallback:** DERP relay over outbound TCP 443. No firewall rule needed (HTTPS egress is implicitly allowed). Slower but always works.

The `default-allow-ssh` (TCP 22) rule is safe to delete because tailnet SSH is wrapped in Tailscale's transport (one of the two above) — never as direct TCP-22 ingress to the VM's public IP. Same logic for `allow-mosh` and `allow-dev-server`.

(NAT punch-through worked without an explicit UDP 41641 rule in our trial — observed behavior, not a stable contract per Tailscale docs. We'll add the rule to make direct connectivity reliable.)

---

## Phase 1 — Trial mosh-via-tailnet

```sh
mosh adam@ai-workstation
```

Use for one work session. If `x` / `c` / `xl` / `xj` / `xk` work normally, proceed.

---

## Phase 2 — Switch clients

### Mac `~/.zshrc`

Backup: `cp ~/.zshrc ~/.zshrc.bak-pre-et-drop-2026-05-08`

Remove:

- Functions: `CVM_ET`, `_x_route`, `_x_iap_active`, `_x_iap_up`, `_x_iap_down`, `_x_iap_status`, `_x_alias_present`, `_x_listener_alive`, `_x_v4_direct`, `_x_sudo`, `vp`, `vp_up`, `vp_down`
- `x iap [up|down|status]` subcommand from `x()`
- `codex-az`'s `vp_up` fallback (function becomes a thin alias to `codex --profile azure`)
- `X` typeset associative array (replace with two scalars)

Add:

```zsh
VM_HOST=ai-workstation
VM_REPO=/home/adam/src/superextra-landing
CVM_MOSH() { mosh adam@$VM_HOST -- bash -ic "$1"; }
```

Updated `x()` (~30 lines vs current ~120):

```zsh
x() {
  _x_title() { printf '\033]0;%s\007' "$1"; }
  case "$1" in
    l)  local name; name=$(_x_pick_remote "Join") || return
        x j "$name" ;;
    j)  [ -n "$2" ] && _x_title "$2" && CVM_MOSH "x j '$2'" || x l ;;
    k)  local name="$2"
        [ -z "$name" ] && { name=$(_x_pick_remote "Kill") || return; }
        ssh "$VM_HOST" "bash -ic 'x k \"$name\"'" ;;
    K)  ssh "$VM_HOST" "bash -ic 'x K'" ;;
    *)  if [ -n "$1" ]; then _x_title "$1"; CVM_MOSH "x '$1'"; else CVM_MOSH "x"; fi ;;
  esac
}
```

`c()` mirrors with `c` as the inner command. `_x_pick_remote` already exists; just update its `ssh` target to `$VM_HOST` (no other change).

### Mac `~/.ssh/config`

Backup: `cp ~/.ssh/config ~/.ssh/config.bak-pre-et-drop-2026-05-08`

Delete:

- `Host superextra-vm` block (entire — public-IP path, unused after switch)
- `Match host superextra-vm,34.38.81.215 exec "..."` ProxyCommand block (IAP fallback)

Slim the existing `Host ai-workstation` block to:

```
Host ai-workstation ai-workstation.tailcb8df5.ts.net 100.101.35.72
    User adam
    HostKeyAlias 34.38.81.215
    ServerAliveInterval 15
    ServerAliveCountMax 10
    TCPKeepAlive no
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 4h
    ObscureKeystrokeTiming no
    IdentitiesOnly yes
    IdentityFile ~/.ssh/id_ed25519
    CheckHostIP no
```

Drop the explicit `Ciphers` / `KexAlgorithms` / `HostKeyAlgorithms` / `PreferredAuthentications` / `RekeyLimit` lines — OpenSSH defaults are fine.

### iPhone Moshi

Edit existing host:

- `HostName` → `ai-workstation.tailcb8df5.ts.net`
- Tailscale must be on. Fall back to literal `100.101.35.72` if MagicDNS misbehaves.

### Validate

- `x test` lands in claude via mosh+tailnet
- `xj test` re-attaches
- `xl` lists/picks/attaches
- `xk test` kills cleanly
- `c test-codex` runs codex
- `xK` wipes (test once, then leave alone)

Rollback if broken: `cp ~/.zshrc.bak-... ~/.zshrc; cp ~/.ssh/config.bak-... ~/.ssh/config; source ~/.zshrc`

---

## Phase 3 — Delete old paths

### Mac

```sh
# IAP fallback machinery
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/co.pachucki.x-netchange.plist || true
rm -f ~/Library/LaunchAgents/co.pachucki.x-netchange.plist
rm -f ~/bin/x-netchange.sh
sudo rm -f /etc/sudoers.d/x-iap-lo0

# Kill any orphan IAP tunnel — anchored to instance name + remote port + flag
pkill -f 'gcloud.*compute[[:space:]]+start-iap-tunnel[[:space:]]+ai-workstation[[:space:]]+2022\b.*--local-host-port=' || true

# Drop lo0 alias
sudo /sbin/ifconfig lo0 -alias 34.38.81.215 || true

# ET binary
brew uninstall et
```

### VM

```sh
ssh ai-workstation '
  set -e
  # Codex v6 proxy bridge
  rm -f ~/bin/codex-connect-proxy.py

  # ET service + package
  sudo systemctl disable --now et.service
  sudo apt remove --purge -y eternalterminal
  sudo rm -rf /etc/systemd/system/et.service.d/
  sudo systemctl daemon-reload

  # fail2ban (vestigial once public SSH is closed)
  sudo fail2ban-client unban --all 2>/dev/null || true
  sudo apt remove --purge -y fail2ban
  sudo rm -rf /var/lib/fail2ban /var/log/fail2ban.log*

  # Verify no orphan f2b firewall rules
  sudo iptables-save 2>/dev/null | grep -i f2b && echo WARN-f2b-iptables-still-present || echo "no f2b iptables rules"
  sudo nft list ruleset 2>/dev/null | grep -i f2b && echo WARN-f2b-nft-still-present || echo "no f2b nft rules"
'
```

### GCP firewall

```sh
# Add Tailscale direct-WG ingress (recommended for stable P2P)
gcloud compute firewall-rules create allow-tailscale-direct \
  --direction=INGRESS --action=ALLOW --rules=udp:41641 \
  --source-ranges=0.0.0.0/0 --description='Tailscale direct WireGuard P2P'

# Delete public terminal/dev ingress
gcloud compute firewall-rules delete -q \
  allow-et allow-mosh default-allow-ssh allow-dev-server
```

### Validate

- `tailscale ping ai-workstation` — pong, ideally `via ...:41641` (direct).
- `ssh ai-workstation 'echo ok'` works via tailnet.
- `mosh adam@ai-workstation` works.
- From a non-tailnet machine: `nc -z -G 3 34.38.81.215 22` should refuse / time out.

---

## Phase 4 — Documentation + cleanup

### Doc rewrite (`docs/vm-setup.md`)

Remove sections:

- "EternalTerminal" subsection
- "IPv6-only network fallback" (entire section)
- vp proxy + codex-connect-proxy.py mentions
- IAP-related operational guidance
- fail2ban section

Add:

- Brief "Tailscale is the transport layer" note (with the mental-model from this plan)
- Updated architecture diagram (single mosh-on-tailnet flow on both clients)

Decision history entry:

> 2026-05-08 — Dropped ET in favor of mosh over Tailscale on both Mac and iPhone. Closed public SSH/mosh/dev-server ingress; added explicit ingress rule for Tailscale direct WireGuard (UDP 41641). Removed IAP fallback machinery (no longer needed: Tailscale handles connectivity via WireGuard direct or DERP relay regardless of v6-only networks). Removed fail2ban (vestigial without public SSH). Recovery: GCP serial console.

### Backup cleanup (gated on Phase 1-3 validation passing)

Once you've used the new setup for a day and everything's working, clean up:

```sh
# Mac
rm -f ~/.zshrc.bak-* ~/.ssh/config.bak-pre-et-drop-*

# VM
ssh ai-workstation 'rm -f ~/.bashrc.bak-*'
```

Don't run this until Phase 4 doc rewrite is also done — the docs reference paths and behaviors that may need quick reference vs. backup files.

---

## Recovery (if Tailscale breaks)

1. **GCP serial console** (always available):
   ```sh
   gcloud compute connect-to-serial-port adam@ai-workstation
   ```
2. **From serial console, re-open public SSH:**
   ```sh
   gcloud compute firewall-rules create default-allow-ssh \
     --direction=INGRESS --action=ALLOW --rules=tcp:22 \
     --source-ranges=0.0.0.0/0 --priority=65534
   ```
3. Then SSH in directly via `34.38.81.215`, debug Tailscale, restore tailnet, re-delete the public SSH rule.

---

## Diff vs. v2

- Tailscale transport wording corrected (direct UDP 41641 vs DERP TCP 443, not "wrapped on 41641").
- `allow-tailscale-direct` promoted from optional to default (added in Phase 3, included in Outcomes).
- `pkill` pattern tightened to anchor on instance name + remote port + flag.
- fail2ban cleanup verifies iptables/nft for orphan rules.
- Backup-file cleanup moved to Phase 4 (gated on validation).
- Recovery command keeps explicit `--priority=65534` for clarity.
