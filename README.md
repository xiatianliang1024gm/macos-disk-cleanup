# macOS Disk Cleanup

An agent skill for auditing and safely reclaiming disk space on macOS.

`https://github.com/xiatianliang1024gm/macos-disk-cleanup`

Built from a real cleanup session on a 233 GB Mac: available space went from 99 GB to
120 GB, with a further 12 GB staged in the Trash — and nearly every "obvious" assumption
turned out to be wrong.

---

## Why this exists

macOS disk management is unusually hostile to common sense. If you (or your agent) reason
about it the way you would on Linux, you will make a chain of wrong calls. Every one of
these was hit for real while building this skill:

| Trap | What actually happens |
|---|---|
| `Operation not permitted` on `~/Library` paths | It is `EPERM` from TCC, **not** a permissions problem. `sudo` does nothing. |
| Checking free space with `df` | `df` excludes APFS *purgeable* space. Measured gap: **7.4 GB**. Use `diskutil`. |
| Deleting `~/Library/Caches/CloudKit` | Holds iCloud sync metadata — triggers a **full iCloud re-sync**. It is only a few MB. |
| `pgrep -if "Code"` to check if VS Code is running | False-matches `com.apple.CodeSigningHelper`, `VTDecoderXPCService`, and every Electron helper. |
| `rm -rf` reporting success | In managed environments it is intercepted and **moved to Trash** — space is not freed. |
| Deleting `~/Library/pnpm` because it is "just cache" | `store/` is cache, but `global/` holds **globally installed CLI tools**. |
| `docker system prune` to reclaim Docker space | The sparse disk image never shrinks. Only Docker Desktop → Clean/Purge data works. |
| A huge "System Data" figure | Much of it is purgeable space that macOS releases on demand. |

The skill encodes all of it, plus a read-only auditor that finds the actual usage.

---

## Install

Copy the skill directory into your agent's skills folder:

```bash
# Claude Code / WorkBuddy-style user skills
git clone https://github.com/xiatianliang1024gm/macos-disk-cleanup.git \
  ~/.workbuddy-ai/skills/macos-disk-cleanup
```

Or drop `SKILL.md`, `scripts/`, and `references/` into any agent that reads skill folders.

---

## Usage

**Run the auditor first.** It is strictly read-only — no deletion, no modification.

```bash
python3 scripts/audit_disk.py
python3 scripts/audit_disk.py --top 25    # more detail per section
```

Output:

1. Real free space (via `diskutil`, with the `df` figure shown for contrast)
2. Local Time Machine and APFS snapshots
3. `~/Library` subdirectory ranking
4. Detail for `Application Support`, `Containers`, `Caches`, `Developer`
5. Safe-to-clean candidates with a total reclaimable figure
6. TCC-protected paths
7. Off-limits paths
8. Next steps

The agent then grades everything into three tiers and executes with guards.

---

## The three tiers

| Tier | Meaning | Action |
|---|---|---|
| 🟢 A | Regenerable cache, no side effects | Safe to clean |
| 🟡 B | Contains user data, or requires in-app action | Clean in-app only — never by hand |
| 🔴 C | System-protected or system files | Never touch |

Full catalog: [`references/cleanup-catalog.md`](references/cleanup-catalog.md)

---

## What makes it safe

The workflow enforces several guards before anything is deleted:

- **Read-only audit first** — deletion is not permitted until the audit is complete and graded
- **Path allowlist** — every target must be confirmed under `$HOME/Library/`
- **App-quit verification** — matched by full main-binary path, never by app name
- **One at a time, verified immediately** — no batch-then-check
- **Trash over `rm`** — recoverable by default
- **Warn → list absolute paths → explain the specific cost → require explicit confirmation**
- **Never verify with `df`** — always `diskutil`
- **Baseline contamination check** — if the user cleaned concurrently, before/after comparisons are invalid

Hard limits are written into the skill: no recursive deletes of `Desktop` / `Downloads` /
`Documents` / `Home` / `/`, no touching `/System`, `/usr`, `/bin`, `/private/var/vm`,
no deleting CloudKit or Docker disk images.

---

## Structure

```
macos-disk-cleanup/
├── README.md                       # this file
├── SKILL.md                        # skill definition: 4-phase workflow, 13 pitfalls, hard limits
├── scripts/
│   └── audit_disk.py               # read-only auditor
└── references/
    └── cleanup-catalog.md          # graded targets, protected paths, command blacklist
```

---

## Verified on

macOS, 233 GB APFS container. Reclaimed ~21 GB in one session (plus ~12 GB staged in the
Trash), while confirming that most of the "obvious" wins were either tiny, protected, or
already handled by the system.

---

## License

Not yet specified. If you intend to reuse this, add a license — without one it is
"all rights reserved" by default.

---

## Contributing

Corrections welcome, especially additional verified traps or per-app cleanup targets.
If you find a target that is documented as safe but is not, please open an issue with the
exact path and the observed behavior.
