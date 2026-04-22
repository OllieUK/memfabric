# Homeserver SSH diagnostic channel for Claude

A narrow, read-only SSH channel that lets the Claude Code session on Windows
run a fixed allow-list of diagnostic commands on homeserver. No interactive
shell, no writes, no port forwarding.

## Threat model

| Concern | Mitigation |
|---|---|
| Stolen key → lateral movement | `ForceCommand` pins every connection to `/usr/local/bin/claude-diag`; `no-pty`, `no-port-forwarding`, `no-agent-forwarding`, `no-X11-forwarding` block the usual escape hatches. |
| Command injection via `$SSH_ORIGINAL_COMMAND` | Script refuses any input containing `; & \| \` $ ( ) < >`. `read -a` + case dispatch, no `eval`. |
| Secret exfiltration (bearer token, `.env` values) | Script never echoes env values; `mcp-probe` only uses `$MCP_BEARER_TOKEN` inside the container, never prints it. |
| Abuse of `docker` group membership | Member of `docker` can normally root the host — but the `ForceCommand` wrapper prevents arbitrary `docker` invocations. The `docker` group is needed only so the wrapper can run `docker compose logs/ps/exec`. |
| Key leaks from Claude's side | Empty-passphrase private key sits on the Windows box; revocation is a one-line delete in `authorized_keys`. |

**Blast radius if exploited:** attacker can read container logs, container
status, and probe `/mcp` from inside the container. No writes, no secrets
printed, no network pivot.

## One-time homeserver install

Run these as root (or via sudo). Commands are deliberately separated — do not
chain them, so that failures surface clearly.

### 1. Create the user

```bash
adduser --disabled-password --gecos "" claude-diag
usermod -aG docker claude-diag
```

### 2. Install the diagnostic script

Copy `scripts/homeserver/claude-diag` from this repo to the server, then:

```bash
install -o root -g root -m 0755 /path/to/claude-diag /usr/local/bin/claude-diag
```

### Homeserver layout (`cit-home-stackdeploy`)

This deployment uses the `cit-home-stackdeploy` split layout:

| Path | Role |
|---|---|
| `/opt/stacks/sources/graph-memory-fabric/` | Git submodule of this repo — the real `docker-compose.yml` lives here. |
| `/opt/stacks/env/services-env/memfabric.env` | The runtime `.env` file for the memfabric stack. |
| `/opt/stacks/deploy/memfabric/compose.yml` | Deploy shim — a tiny compose file that sets the project `name: memfabric` and `include:`s the sources compose file. This is what `docker compose` points at. |

The script defaults match this layout (`COMPOSE_DIR=/opt/stacks/deploy/memfabric`,
`COMPOSE_FILE=compose.yml`). If stackdeploy changes the convention, override via
`/etc/environment`:

```
CLAUDE_DIAG_COMPOSE_DIR=/opt/stacks/deploy/memfabric
CLAUDE_DIAG_COMPOSE_FILE=compose.yml
```

Smoke test as root:

```bash
sudo -u claude-diag env SSH_ORIGINAL_COMMAND="version" /usr/local/bin/claude-diag
```

You should see the script version, hostname, and compose dir. No errors.

**Note:** `sudo` strips most environment variables by default. `env VAR=value cmd`
injects `VAR` into the process environment after sudo has finished. Do not write
`SSH_ORIGINAL_COMMAND="version" sudo -u claude-diag ...` — the var never crosses
the sudo boundary and the script receives an empty command.

### 3. Install the authorized_keys entry

Create `~claude-diag/.ssh/authorized_keys` owned by `claude-diag:claude-diag`,
mode `0600`, containing **exactly one line**:

```
command="/usr/local/bin/claude-diag",no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty,restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINhBFUA7kXgEvm0cuCt4c3QQNXheYii2gZcGzZmxpRk3 claude-diag@windows
```

Commands:

```bash
install -d -o claude-diag -g claude-diag -m 0700 ~claude-diag/.ssh
# paste the line above into ~claude-diag/.ssh/authorized_keys using your editor
chown claude-diag:claude-diag ~claude-diag/.ssh/authorized_keys
chmod 0600 ~claude-diag/.ssh/authorized_keys
```

The `restrict` keyword is belt-and-braces — it disables every forwarding/pty
feature currently known and any added in future OpenSSH releases, before the
explicit `no-*` options re-apply the same restrictions.

### 4. sshd policy

If `/etc/ssh/sshd_config` uses `AllowUsers` or `AllowGroups`, add `claude-diag`
(or the group it's in) to the allow-list. Do **not** globally loosen sshd.

If you're on a cloud-provider default config (no AllowUsers/Groups), no
change is needed — but consider adding the following block to **homeserver's
`/etc/ssh/sshd_config`** (this is a server-side file — these directives are
not valid in Windows `~/.ssh/config`):

```
Match User claude-diag
    PasswordAuthentication no
    AuthenticationMethods publickey
    PermitTTY no
    X11Forwarding no
    AllowTcpForwarding no
    AllowAgentForwarding no
    PermitTunnel no
    GatewayPorts no
```

> ⚠ `AuthenticationMethods`, `PermitTTY`, `X11Forwarding`, `AllowTcpForwarding`,
> `AllowAgentForwarding`, `PermitTunnel`, and `GatewayPorts` are **sshd**
> directives. The Windows client's `ssh` binary will reject the whole config
> file with `Bad configuration option` if any of these end up in
> `C:\Users\olive\.ssh\config`. Keep client config (Section: Windows-side
> setup) and server config (here) cleanly separated.

Reload sshd:

```bash
sshd -t && systemctl reload ssh
```

`sshd -t` validates the config before reload — if this prints anything, do
not reload. Fix the error first.

### 5. Network exposure

SSH on homeserver is currently restricted. For `claude-diag` access, pick one:

- **Preferred (once Tailscale is up):** bind sshd to the Tailnet interface
  only via `ListenAddress`, or use a `Match Address 100.64.0.0/10` block.
  Claude connects to the Tailnet name.
- **Interim (public SSH with IP allow-list):** add your Windows outbound IP
  to the existing allow-list. Revisit once Tailscale lands.

## Windows-side setup

### `~/.ssh/config` entry

Append to `C:\Users\olive\.ssh\config` (create if absent):

```
Host homeserver-diag
    HostName server.home.carr-it.net
    User claude-diag
    IdentityFile ~/.ssh/claude_diag_ed25519
    IdentitiesOnly yes
    StrictHostKeyChecking accept-new
    # Once Tailscale is in place, swap HostName to the tailnet name.
```

`IdentitiesOnly yes` stops ssh from offering every key in your agent to
homeserver, which would look like a brute-force attempt in the auth log.

### Claude permission allow-list

Add to `.claude/settings.local.json` (project-local) under `permissions.allow`:

```
"Bash(ssh homeserver-diag:*)"
```

(Exact key spelling depends on your current settings.json shape — merge
carefully rather than overwriting.)

### Smoke test

From the Windows side:

```powershell
ssh homeserver-diag version
```

Expected output:

```
claude-diag script version: 1.0.0
host: <homeserver-hostname>
compose dir: /opt/stacks/memfabric
service: memfabric-api
date: 2026-04-22T...Z
```

If that works, Claude can now run `logs`, `status`, `mcp-probe`, `routes`,
`help`, `version` directly.

## Revocation

To cut Claude's access instantly:

```bash
rm ~claude-diag/.ssh/authorized_keys
```

The key is dead. The user account is harmless on its own (no password, no
other keys). To remove the account entirely:

```bash
userdel -r claude-diag
```

## Extending the allow-list

New subcommands go in `scripts/homeserver/claude-diag` inside this repo, go
through code review, and are deployed to `/usr/local/bin/claude-diag` by you.
**Never extend the script in place on homeserver** — the repo is the source
of truth and a drift between them is how these things quietly grow teeth.
