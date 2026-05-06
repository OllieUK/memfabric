# Memfabric backup and restore

This doc covers what backup discipline is currently in place. Treat it as the
minimum viable defence — proper hardening is tracked under WP-166.

## What is backed up

Two complementary outputs per nightly run, both in `/opt/stacks/backups/memfabric/`:

| File | Contents | Restore mechanism | Coverage |
|---|---|---|---|
| `dump_YYYY-MM-DD.json` | All `:Memory` nodes + 15 edge types as JSON. | `scripts/restore_db.py --from <file>` after `seed_strands.py` runs on a clean DB. | Memory layer + knowledge-layer edges. **Misses** Strand, Agent, Person, Project, Task, and knowledge-layer node types. |
| `volume_YYYY-MM-DD.tar.gz` | Full tar of the `memfabric_memgraph_lib` docker volume. | Stop stack, `tar xzf` into a fresh volume, restart. See restore procedure below. | **Everything** — all nodes, all edges, all indexes, all internal Memgraph state. |

The two formats are kept side-by-side because each defends against a different
failure mode:

- **JSON dump** is portable across Memgraph versions, human-inspectable, and
  diff-able between days. Useful for forensics, partial restore, or migration.
  But it can't reconstruct strand catalogue or knowledge layer alone.
- **Volume tarball** is opaque binary tied to the Memgraph version that wrote
  it, but captures everything. Useful for full disaster recovery.

If both fail, the orphaned volumes from a prior deploy may still be on disk —
check `docker volume ls | grep memgraph` before assuming total loss.

## Schedule

Nightly at 02:30 UTC (just before Memgraph long-rest at 03:00 UTC). The cron
entry runs as **root** (same pattern as other host backups, ensures correct
permissions on `/opt/stacks/backups/memfabric/` and unrestricted docker
socket access):

```
30 2 * * * /opt/stacks/sources/graph-memory-fabric/scripts/homeserver/backup-nightly.sh >> /opt/stacks/backups/memfabric/backup.log 2>&1
```

Install via `sudo crontab -e`. The script lives in the repo at
`scripts/homeserver/backup-nightly.sh` and is invoked from the deployed git
checkout. Backup files are owned by root — inspect them via `sudo` from
oliver's shell, or via `sudo -u oliver cat ...` if you need them readable as
oliver.

## Retention

Files older than 14 days (configurable via `RETENTION_DAYS` env var) are
pruned at the end of each run. At ~600 MB per volume tarball + a few MB JSON,
14 days of backups is roughly 10 GB on the RAID array — trivial.

## Restore procedure

### From JSON dump (partial — Memory layer only)

1. Stop the api: `dcumf stop memfabric-api`.
2. Connect to Memgraph and clear the Memory layer:
   `MATCH (m:Memory) DETACH DELETE m`.
3. Reseed strands if missing: `python3 scripts/seed_strands.py`.
4. Restore: `python3 scripts/restore_db.py --from /opt/stacks/backups/memfabric/dump_YYYY-MM-DD.json`.
5. Restart the api: `dcumf up -d memfabric-api`.

### From volume tarball (full — everything)

1. Stop the entire stack: `dcumf down` (without `-v`, never `-v`).
2. Inspect what volume the Memgraph container is wired to:
   `docker volume ls | grep memgraph_lib`.
3. Backup the current volume contents before overwriting (paranoid but cheap):
   ```
   docker run --rm -v memfabric_memgraph_lib:/src:ro \
       -v /opt/stacks/backups/memfabric:/backup alpine \
       tar czf /backup/volume_pre-restore_$(date +%Y%m%d_%H%M).tar.gz -C /src .
   ```
4. Empty the volume:
   ```
   docker run --rm -v memfabric_memgraph_lib:/v alpine sh -c 'rm -rf /v/*'
   ```
5. Restore from the tarball:
   ```
   docker run --rm -v memfabric_memgraph_lib:/v \
       -v /opt/stacks/backups/memfabric:/backup alpine \
       tar xzf /backup/volume_YYYY-MM-DD.tar.gz -C /v
   ```
6. Restart: `dcumf up -d`.
7. Verify: `curl https://memfabric.carr-it.net/strands` returns the catalogue;
   `/memory/maintenance/stats` shows the expected node count.

## Known gaps (tracked in WP-166)

- **No off-host replication.** Single point of failure: the homeserver itself.
- **No restore-test discipline.** We do not periodically verify that backups
  are usable end-to-end.
- **Runs as root.** Matches the host's other backup discipline. Should
  eventually run as a dedicated stack-user with read-only access to source
  dirs and write-only access to backup dirs (similar to the `claude-diag`
  pattern). Root is more privileged than necessary; the `claude-diag`-style
  least-privilege user is the target end-state.
- **No cold storage.** No defence against ransomware or sustained host
  compromise.
- **No alerting on failure.** Cron failures land in `backup.log`; nobody is
  paged.

## Manual backup before risky operations

Run the same script ad-hoc whenever about to do something that could damage
the fabric (deploys, schema changes, large ingests). Invoke as root to match
the cron path and produce files with consistent ownership:

```
sudo /opt/stacks/sources/graph-memory-fabric/scripts/homeserver/backup-nightly.sh
```

It is safe to run while another invocation is in progress (file lock prevents
overlap).
