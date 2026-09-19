# Cleanup Catalog

Graded by risk. Complete the read-only audit before deleting anything.

---

## 🟢 Tier A: regenerable cache, no side effects

| Target | Path (relative to `~`) | Side effect |
|---|---|---|
| Chrome Service Worker | `Library/Application Support/Google/Chrome/<Profile>/Service Worker` | PWA offline data cleared; sites load slowly on first visit |
| Chrome Code Cache | `Library/Application Support/Google/Chrome/<Profile>/Code Cache` | Slower first load per site |
| VS Code extension VSIX cache | `Library/Application Support/Code/CachedExtensionVSIXs` | None (extensions themselves unaffected) |
| Lark old update packages | `Library/Application Support/LarkShell/update/update.noindex` | Next update re-downloads |
| WeCom embedded browser cache | `Library/Containers/com.tencent.WeWorkMac/Data/Documents/cefcache` | Embedded browser slower on first load |
| Slack cache | `Library/Application Support/Slack/Cache` | Slower first load |
| npm / Yarn / pip cache | `.npm/_cacache`, `.cache/yarn`, `Library/Caches/pip` | Next install re-downloads |
| pnpm store | `Library/pnpm/store` (**delete `store` only** — never the sibling `global`/`bin`) | Next install re-downloads |
| Homebrew cache | `Library/Caches/Homebrew` | Next install re-downloads |
| Gradle / CocoaPods cache | `.gradle/caches`, `Library/Caches/CocoaPods` | Next build re-downloads |
| Xcode DerivedData | `Library/Developer/Xcode/DerivedData` | Slower next build (safe) |
| Xcode device support | `Library/Developer/Xcode/iOS DeviceSupport` | Regenerated when connecting an older device |
| iOS Simulator data | `Library/Developer/CoreSimulator/Devices` | Simulator contents cleared (prefer the targeted `xcrun simctl delete unavailable`) |
| Generic caches | `Library/Caches/*` | Slower first launch per app |

> Chrome profile directory names vary: `Default`, `Profile 1`, `Profile 2`, … Enumerate them first.

---

## 🟡 Tier B: contains user data or requires in-app action — never delete by hand

| Target | Correct approach | Cost of deleting by hand |
|---|---|---|
| WeCom chat history | In-app: Settings → General → Storage → Clear cache | Loses work chats and received files |
| WeChat chat history | In-app: Settings → General → Storage | Loses chat history |
| Lark chat cache | In-app: Settings → Clear cache | Loses chat history |
| Docker virtual disk | `docker system prune -a --volumes`, then Docker Desktop → Troubleshoot → Clean/Purge data | **Corrupts the Docker environment** |
| JetBrains indexes | In-IDE: File → Invalidate Caches | Corrupted indexes requiring rebuild |
| iOS backups | System Settings → General → Storage, or Finder device management | Loses the phone backup |
| Mail attachments | Manage inside the Mail app | Attachments lost; messages may not open |
| Cloud drive local cache (Baidu Netdisk, etc.) | Clear cache in-app | Full re-sync required |
| Time Machine local snapshots | `sudo tmutil thinlocalsnapshots / <bytes> 4` | Does not affect backups on the external drive |

---

## 🔴 Tier C: never touch

### System-protected directories (`rm` returns `Operation not permitted`; `sudo` is useless)

| Path | Reason |
|---|---|
| `Library/Caches/CloudKit` | iCloud sync metadata; deleting triggers a full iCloud re-sync |
| `Library/Caches/FamilyCircle` | Family Sharing configuration |
| `Library/Containers/com.apple.geod` | Location Services container |
| `Library/Application Support/com.apple.TCC` | Privacy permissions database |
| `Library/Safari`, `Library/Mail`, `Library/Messages`, `Library/Cookies` | User data |

### System files

- `/System`, `/usr`, `/bin`, `/sbin`
- `/private/var/vm` (swap files)
- All of `/Library/Application Support` (breaks multiple apps)
- All of `~/Library`
- Any unrecognised `/Library/Application Support/<name>` directory

### System snapshots

- `com.apple.os.update-*` — `Purgeable: No`, limits the minimum APFS container size, expected and normal

---

## Dangerous-command blacklist

These command patterns are never executed:

```bash
rm -rf ~/Library                                          # destroys all app data
rm -rf ~/Library/Caches/CloudKit                          # triggers full iCloud re-sync
rm -rf ~/Library/Containers/com.docker.docker/Data/vms    # corrupts Docker
rm -rf ~/Library/Application\ Support/MobileSync/Backup   # loses phone backups
rm -rf ~/Desktop/*  ~/Downloads/*  ~/Documents/*          # personal files
rm -rf /System /usr /bin /sbin /private/var/vm
sudo rm -rf /                                             # catastrophe
```

---

## Determining whether an app has quit

The app must be closed before deleting its container cache. **Always match the full main-binary path**:

| App | Check command |
|---|---|
| VS Code | `pgrep -f "Visual Studio Code.app/Contents/MacOS/Electron"` |
| Chrome | `pgrep -f "Google Chrome.app/Contents/MacOS/Google Chrome"` |
| WeCom | `pgrep -f "企业微信.app/Contents/MacOS"` |
| Lark | `pgrep -f "Lark.app/Contents/MacOS"` |
| Docker | `pgrep -f "Docker.app/Contents/MacOS/Docker"` |

**Counter-examples (false positives)**:

```bash
pgrep -if "Code"    # matches com.apple.CodeSigningHelper, VTDecoderXPCService,
                    # and every Electron app's helper processes
pgrep -if "Docker"  # may match unrelated processes
```

---

## Verifying results

**Step 0: empty the Trash.** In managed environments `rm` is proxied to Trash — the command succeeds but space is not freed.
Telltale signs: `[safe-delete] genie-trash`, `FSMoveObjectToTrashSync`, `SAFE_DELETE_FAIL_CLOSED`.
App containers (e.g. `com.apple.geod`) cannot be moved to Trash and fail with `status -5000` — expected, skip them.

**Never use `df`.** It excludes APFS purgeable space and under-reports by a wide margin, enough to make a successful cleanup look like it failed.

```bash
diskutil info /System/Volumes/Data | grep "Container Free Space"   # the only trustworthy source
```

Cross-check by looking at the target directory's own size change — re-run `du -sh` on the path you just cleaned. A directory that drops by an order of magnitude proves the deletion took effect better than total free space does (free space is also affected by purgeable space, snapshots, and anything the user did concurrently).

**`~/.Trash` is TCC-protected and cannot be enumerated.** `ls ~/.Trash` returns `Operation not permitted`. Confirming an emptied Trash requires the user to check in Finder, or inferring from the modification time of `ls -ld ~/.Trash`.

If total space moved differently than expected, check in order: ① is the Trash empty; ② did the user clean things concurrently (baseline contamination); ③ has APFS purgeable space not yet been reclaimed.
