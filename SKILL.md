---
name: macos-disk-cleanup
description: This skill should be used when diagnosing or reclaiming disk space on macOS. Trigger it whenever the user reports a full disk or low disk space, wants to free up or clean up storage, or asks what is consuming their disk — including phrasings such as "磁盘空间不足", "磁盘满了", "清理磁盘空间", "释放空间", "存储空间不够", and any question about the "System Data" / "系统数据" category being too large. Also trigger it when System Settings and `df` disagree about free space, when `rm` fails with "Operation not permitted" under ~/Library, or when any cache cleanup is being planned or executed. Covers read-only auditing, risk-graded classification, and guarded execution.
agent_created: true
---

# macOS Disk Cleanup

## Purpose

Locate real disk usage on macOS, separate "safe to delete" from "system-protected, do not touch", and execute cleanup according to a risk grading.

**What this skill delivers is the process, not a size list.** Which directories are large is entirely machine-specific — it depends on what the user has installed, which apps they run, and which toolchains they build with. Do **not** carry over concrete sizes or "the big wins are X and Y" conclusions from one machine to another. What transfers is: how to measure correctly, how to tell cache from user data, which paths are protected, and in what order to act.

This workflow exists because macOS disk accounting and deletion behavior are **deeply counter-intuitive**. Judging by common sense leads to a chain of mistakes (see "Critical Pitfalls"). **Execute the four phases in order — never skip straight to deletion.**

## When to use

- The user reports a full disk or low disk space ("磁盘空间不足", "磁盘满了", "空间不够用了")
- The user wants to free up or clean up disk space ("清理磁盘空间", "释放空间", "清理缓存")
- The user asks what is consuming their disk, or why the "System Data" / "系统数据" category is so large
- System Settings and `df` disagree about free space
- `rm` fails with `Operation not permitted` and the user assumes it is a permissions issue and reaches for `sudo`
- Any cache cleanup under `~/Library` is being planned
- The user needs to know whether a given directory can be deleted

## Four-phase workflow

### Phase 1: Read-only audit (delete nothing)

Run the bundled script for a full scan:

```bash
python3 scripts/audit_disk.py
```

The script is **strictly read-only** and reports: real free space, APFS snapshots, `~/Library` subdirectory ranking, and TCC-protected paths.

For manual spot checks:

```bash
diskutil info /System/Volumes/Data | grep "Container Free Space"   # real free space
tmutil listlocalsnapshots /                                        # local snapshots
diskutil apfs listSnapshots /                                      # APFS snapshots
du -sh ~/Library/* 2>/dev/null | sort -rh | head -15
```

**No deletion may occur before the audit is complete.** If the user asks to "just clean it up", complete the audit and present the graded list first, then proceed to Phase 3.

### Phase 2: Risk grading

Sort every item into one of three classes and present the table to the user:

| Tier | Meaning | Action |
|---|---|---|
| 🟢 Tier A | Regenerable cache, no side effects | Safe to batch-clean |
| 🟡 Tier B | Contains user data or requires in-app action | Guide the user to clean in-app; **never delete by hand** |
| 🔴 Tier C | System-protected or system files | Never touch |

See `references/cleanup-catalog.md` for the detailed target list.

### Phase 3: Guarded execution

Every one of the following checks is mandatory:

1. **Confirm the app has quit.** Before deleting an app container's cache, the app must be closed, or state may be corrupted or deletion may fail.
   Match the **full path of the main binary** — never match the app name alone:

   ```bash
   pgrep -f "Visual Studio Code.app/Contents/MacOS/Electron"   # correct
   pgrep -if "Code"                                            # wrong, false-matches
   ```

2. **Path allowlist check.** Every target path must be explicitly confirmed to live under `$HOME/Library/`:

   ```bash
   case "$p" in
     "$HOME/Library/"*) ;;
     *) echo "path check failed, skipping: $p"; continue ;;
   esac
   ```

3. **Delete one item at a time and verify immediately** — do not batch-delete and check afterwards:

   ```bash
   sz=$(du -sh "$p" 2>/dev/null | cut -f1)
   rm -rf "$p" 2>/dev/null
   [ -e "$p" ] && echo "⚠ leftover ($sz): $p" || echo "✓ removed ($sz): $p"
   ```

4. **Prefer moving to Trash** (recoverable). Use `rm -rf` only when the user explicitly chose permanent deletion and understands the risk.
   Note: in managed environments `rm` itself may be intercepted and routed to Trash (see pitfall 11), so **after deleting, always tell the user to empty the Trash in Finder**, otherwise the space is never actually reclaimed.

5. **Warn, list, then require explicit confirmation.** Before any irreversible deletion, provide:
   a bold warning + the full list of absolute paths + the specific risk for each item (what is lost, what the cost is) + explicit user confirmation.

### Phase 4: Verification and reconciliation

**Step 0: Confirm the Trash is empty.** If deletion was intercepted by the safe-delete layer (pitfall 11), the content only moved to Trash and the space is not yet free. Ask the user to empty the Trash in Finder before verifying.

**Never judge cleanup results with `df`.** `df` excludes APFS purgeable space and under-reports by a wide margin — enough to make a successful cleanup look like it did nothing.

```bash
diskutil info /System/Volumes/Data | grep "Container Free Space"   # the only trustworthy source
```

**Beware baseline contamination.** The user may clean things themselves during the diagnosis, which invalidates before/after comparisons. Therefore:

- Record a baseline snapshot during the audit (per-directory sizes + Container Free Space)
- Re-measure after execution and cross-check against the **size change of the target directories**, not just total free space
- If total space moved differently than expected, confirm whether the user acted concurrently before drawing conclusions

## Critical pitfalls

Each of these will be hit by anyone relying on common sense:

1. **`Operation not permitted` is not a permissions problem.** It is `EPERM`, blocked at the syscall layer by macOS TCC / the data vault. **`sudo` is completely useless.**
   How to tell them apart: `Permission denied` (EACCES) is a permissions-bit issue. Verification method — `ls -ld` shows correct owner and mode, yet `du`/`rm` are refused when reading the contents.

2. **`df` under-reports free space.** Always use `Container Free Space` from `diskutil info /System/Volumes/Data`.

3. **`~/Library/Caches/CloudKit` and `FamilyCircle` must not be deleted.**
   CloudKit holds iCloud sync metadata; deleting it triggers a **full iCloud re-sync**. They are typically only a few MB — zero benefit, enormous cost.

4. **Fuzzy matches like `pgrep -if "Code"` produce false positives.** They match `com.apple.CodeSigningHelper`, `VTDecoderXPCService`, and Electron apps' own helper processes. Always match the full main-binary path.

5. **System update snapshots must not be deleted.** `com.apple.os.update-*` has `Purgeable: No` and the note "limits the minimum size of APFS Container". It is expected and normal.

6. **Docker's sparse disk image never shrinks by itself.** After `docker system prune` empties its contents, the host-side `Data/vms` file keeps its size. Reclaim it via Docker Desktop → Troubleshoot → Clean/Purge data. **Deleting `Data/vms` by hand corrupts Docker.**

7. **Chat apps' media files are the real heavyweights.** WeChat / WeCom / Lark chat files routinely reach several GB to tens of GB, and **must be cleaned in-app**. Deleting `Documents/Profiles` by hand means losing work history.

8. **Never use third-party "one-click cleaner" utilities.** They routinely delete critical caches like CloudKit, causing iCloud re-syncs or broken apps.

9. **Timing for app container directories.** Contents under `~/Library/Containers/<bundle-id>/` are only safe to delete after the app has quit.

10. **A large "System Data" reading does not mean real usage.** A significant portion is macOS purgeable space, released automatically when needed.

11. **`rm` may be intercepted by a safe-delete layer and merely move files to Trash.** In managed environments, deletion commands are proxied to Trash — **the command returns success but space is not freed.**
    Telltale signs: output containing `[safe-delete] genie-trash`, `FSMoveObjectToTrashSync`, or `SAFE_DELETE_FAIL_CLOSED`.
    Two consequences follow:
    - **"Deletion succeeded" ≠ "space was reclaimed."** After cleanup, always tell the user to empty the Trash in Finder.
    - **App containers cannot be moved to Trash.** They fail with `FSMoveObjectToTrashSync failed (status -5000)`. This is **expected behavior, not a permissions problem** — skip them, and do not try to "fix" it with `sudo`.

12. **`~/.Trash` is itself TCC-protected.** An agent cannot enumerate the Trash (`ls ~/.Trash` returns `Operation not permitted`). Confirming the result requires the user to look in Finder, or inferring from the modification time of `ls -ld ~/.Trash`.

13. **During the audit, inspect directory *composition*, not just size.** A single directory can mix "pure cache" with "software the user installed", and the *smaller* child is often the one that matters.
    Example: `~/Library/pnpm` looks like pure package-manager cache, but it contains three different things — `store` is a content-addressable cache (deletable), `global` holds **globally installed CLI tools** (deleting it silently uninstalls the user's global packages), and `bin/` holds global binaries. Judging by the directory name alone destroys working tooling while reclaiming almost nothing.
    **Before deleting any directory, run `du -sh <dir>/*` to confirm what each child actually is.**

## Hard limits

The following are never performed, even if the user asks:

- Recursively emptying `Desktop` / `Downloads` / `Documents` / `Home` / `/`
- Touching `/System`, `/usr`, `/bin`, `/sbin`, `/private/var/vm`
- Deleting all of `~/Library` or `/Library/Application Support`
- Deleting TCC-protected directories such as CloudKit / FamilyCircle
- Hand-deleting Docker `Data/vms`, or chat apps' `Profiles` / `Documents`

## Bundled resources

- `scripts/audit_disk.py` — read-only diagnostic script producing a graded audit report
- `references/cleanup-catalog.md` — per-app cleanup targets, TCC-protected paths, and a blacklist of dangerous operations
