# macOS Disk Cleanup

An agent skill for auditing and safely reclaiming disk space on macOS.

`https://github.com/xiatianliang1024gm/macos-disk-cleanup`

Built from a real cleanup session on macOS — one where nearly every "obvious" assumption
turned out to be wrong.

**What this skill actually provides is a process, not a size table.** How much space you
reclaim depends entirely on what happens to be installed on your machine: caches,
containers, developer toolchains, chat apps. Treat the workflow, the guards, and the
pitfall list as the deliverable — the numbers are incidental.

---

## Why this exists

macOS disk management is unusually hostile to common sense. If you (or your agent) reason
about it the way you would on Linux, you will make a chain of wrong calls. Every one of
these was hit for real while building this skill:

| Trap | What actually happens |
|---|---|
| `Operation not permitted` on `~/Library` paths | It is `EPERM` from TCC, **not** a permissions problem. `sudo` does nothing. |
| Checking free space with `df` | `df` excludes APFS *purgeable* space and under-reports by a wide margin. Use `diskutil`. |
| Deleting `~/Library/Caches/CloudKit` | Holds iCloud sync metadata — triggers a **full iCloud re-sync**. Typically only a few MB, so the payoff is zero and the cost is enormous. |
| `pgrep -if "Code"` to check if VS Code is running | False-matches `com.apple.CodeSigningHelper`, `VTDecoderXPCService`, and every Electron helper. |
| `rm -rf` reporting success | In managed environments it is intercepted and **moved to Trash** — space is not freed. |
| Deleting `~/Library/pnpm` because it is "just cache" | `store/` is cache, but `global/` holds **globally installed CLI tools**. |
| `docker system prune` to reclaim Docker space | The sparse disk image never shrinks. Only Docker Desktop → Clean/Purge data works. |
| A huge "System Data" figure | Much of it is purgeable space that macOS releases on demand. |

The skill encodes all of it, plus a read-only auditor that finds the actual usage.

> Specific sizes are deliberately omitted throughout. A directory that dominates one
> machine may not even exist on another; what transfers between machines is *how to tell*
> cache from user data, *what* is protected, and *in what order* to act.

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
├── LICENSE                         # MIT
├── SKILL.md                        # skill definition: 4-phase workflow, 13 pitfalls, hard limits
├── scripts/
│   └── audit_disk.py               # read-only auditor
└── references/
    └── cleanup-catalog.md          # graded targets, protected paths, command blacklist
```

---

## Design principles

Worth stating explicitly, because they are what makes this reusable across machines:

1. **Process over numbers.** No hardcoded size thresholds, no "delete these 10 paths".
   The workflow tells you how to *find* and *classify* targets on whatever machine you are on.
2. **Enumerate before judging.** Never infer a directory's nature from its name — a
   "cache" folder can hold global CLI tools. Inspect its children first.
3. **Read-only until graded.** Auditing and deleting are strictly separated phases.
4. **Reversible by default.** Trash over `rm`; permanent deletion requires explicit consent.
5. **Verify with the right instrument.** The wrong tool (`df`) silently gives the wrong
   answer, which is worse than no answer.

---

## Verified on

macOS (APFS). The workflow has been exercised end to end through all four phases. The
notable finding was not the space reclaimed but the shape of the result: most of the
"obvious" wins turned out to be tiny, protected, or already handled by the system — which
is precisely why the audit-first, grade-then-act order matters.

Because results are machine-specific, this repo does not publish a benchmark. Run
`scripts/audit_disk.py` on your own machine to see your own numbers.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Contributing

Corrections welcome, especially additional verified traps or per-app cleanup targets.
If you find a target that is documented as safe but is not, please open an issue with the
exact path and the observed behavior.
