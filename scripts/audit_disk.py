#!/usr/bin/env python3
"""
Read-only macOS disk space auditor.

Purpose: locate real disk usage, identify safely-deletable items and
system-protected paths.

Safety: this script is STRICTLY READ-ONLY. It performs no deletion,
move, or modification of any kind.

Usage:
    python3 audit_disk.py            # standard audit
    python3 audit_disk.py --top 25   # change per-section item count
"""

import argparse
import glob
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
TOP = 15

# Known safe-to-clean targets: (label, path relative to HOME)
SAFE_TARGETS = [
    ("Chrome Service Worker cache", "Library/Application Support/Google/Chrome/{p}/Service Worker"),
    ("Chrome Code Cache", "Library/Application Support/Google/Chrome/{p}/Code Cache"),
    ("VS Code extension VSIX cache", "Library/Application Support/Code/CachedExtensionVSIXs"),
    ("VS Code cache", "Library/Application Support/Code/Cache"),
    ("Lark old update packages", "Library/Application Support/LarkShell/update/update.noindex"),
    ("WeCom embedded browser cache", "Library/Containers/com.tencent.WeWorkMac/Data/Documents/cefcache"),
    ("Slack cache", "Library/Application Support/Slack/Cache"),
    ("Postman cache", "Library/Application Support/Postman/Cache"),
    ("npm cache", ".npm/_cacache"),
    ("pnpm store (never delete sibling global/bin)", "Library/pnpm/store"),
    ("Yarn cache", ".cache/yarn"),
    ("pip cache", "Library/Caches/pip"),
    ("Homebrew cache", "Library/Caches/Homebrew"),
    ("Gradle cache", ".gradle/caches"),
    ("CocoaPods cache", "Library/Caches/CocoaPods"),
    ("Xcode DerivedData", "Library/Developer/Xcode/DerivedData"),
    ("Xcode iOS DeviceSupport", "Library/Developer/Xcode/iOS DeviceSupport"),
    ("iOS Simulator devices", "Library/Developer/CoreSimulator/Devices"),
]

# Known TCC / data-vault protected paths: rm fails with "Operation not permitted"
PROTECTED = [
    "Library/Caches/CloudKit",
    "Library/Caches/FamilyCircle",
    "Library/Containers/com.apple.geod",
    "Library/Application Support/com.apple.TCC",
    "Library/Safari",
    "Library/Mail",
    "Library/Messages",
    "Library/Cookies",
]

# Absolutely off-limits
FORBIDDEN = [
    "Library/Containers/com.docker.docker/Data/vms",
    "Library/Application Support/MobileSync/Backup",
]


def human(n):
    n = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if abs(n) < 1024 or unit == "T":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024


def run(cmd, timeout=600):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def du_many(paths):
    """Get sizes in bulk with a single du call. Returns [(bytes, path)] descending."""
    paths = [p for p in paths if os.path.lexists(p)]
    if not paths:
        return []
    results = []
    for i in range(0, len(paths), 150):
        chunk = paths[i:i + 150]
        out = run(["du", "-sk"] + chunk)
        for line in out.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            try:
                results.append((int(parts[0]) * 1024, parts[1]))
            except ValueError:
                continue
    results.sort(reverse=True)
    return results


def children(path):
    try:
        return sorted(
            e.path for e in os.scandir(path) if e.is_dir(follow_symlinks=False)
        )
    except OSError:
        return []


def access_error(path):
    """Return 'ok' / 'EPERM' / 'missing'."""
    if not os.path.lexists(path):
        return "missing"
    try:
        with os.scandir(path) as it:
            next(it, None)
        return "ok"
    except OSError as e:
        return "EPERM" if e.errno == 1 else f"E{e.errno}"


def section(title):
    print()
    print("=" * 62)
    print(title)
    print("=" * 62)


def main():
    global TOP
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    TOP = args.top

    print("macOS read-only disk space audit")
    print(f"Home directory: {HOME}")
    print("This script performs no deletion")

    # ---- 1. Disk overview ----
    section("1. Disk overview (trust diskutil; df under-reports purgeable space)")
    info = run(["diskutil", "info", "/System/Volumes/Data"])
    free = total = None
    for line in info.splitlines():
        if "Container Free Space:" in line:
            free = line.split(":", 1)[1].strip()
        if "Container Total Space:" in line:
            total = line.split(":", 1)[1].strip()
    if free:
        print(f"  Container free space (real): {free}")
    if total:
        print(f"  Container total space:       {total}")

    dfout = run(["df", "-k", "/System/Volumes/Data"])
    for line in dfout.splitlines()[1:]:
        f = line.split()
        if len(f) >= 4:
            try:
                print(f"  df reports available:        {human(int(f[3]) * 1024)}  "
                      f"(usually lower than reality; do not rely on it)")
            except ValueError:
                pass

    # ---- 2. Snapshots ----
    section("2. Snapshot usage")
    tml = run(["tmutil", "listlocalsnapshots", "/"])
    snaps = [l for l in tml.splitlines()[1:] if l.strip()]
    if snaps:
        print(f"  Time Machine local snapshots: {len(snaps)}")
        for s in snaps[:10]:
            print(f"    {s.strip()}")
        print("  -> reclaim with: tmutil thinlocalsnapshots / <bytes> 4")
    else:
        print("  Time Machine local snapshots: none (skip the snapshot step)")

    apfs = run(["diskutil", "apfs", "listSnapshots", "/"])
    if "com.apple.os.update" in apfs:
        print("  APFS system update snapshot: present (normal, Purgeable: No, never delete)")

    # ---- 3. ~/Library subdirectories ----
    section(f"3. ~/Library subdirectory usage (top {TOP})")
    lib = os.path.join(HOME, "Library")
    for size, path in du_many(children(lib))[:TOP]:
        print(f"  {human(size):>9}  {os.path.relpath(path, HOME)}")

    # ---- 4. Key subdirectory detail ----
    for sub in ("Application Support", "Containers", "Caches", "Developer"):
        target = os.path.join(lib, sub)
        if not os.path.isdir(target):
            continue
        items = du_many(children(target))
        if not items:
            continue
        section(f"4. Library/{sub} detail (top {TOP})")
        for size, path in items[:TOP]:
            print(f"  {human(size):>9}  {os.path.relpath(path, HOME)}")

    # ---- 5. Safe-to-clean candidates ----
    section("5. Safe to clean (Tier A, no side effects)")
    chrome_dirs = []
    for pat in ("Default", "Profile *"):
        chrome_dirs += [
            os.path.basename(p)
            for p in glob.glob(os.path.join(
                lib, "Application Support/Google/Chrome", pat))
            if os.path.isdir(p)
        ]
    found = []
    for label, rel in SAFE_TARGETS:
        if "{p}" in rel:
            for p in chrome_dirs:
                found.append((label.replace("{p}", p), os.path.join(HOME, rel.format(p=p))))
        else:
            found.append((label, os.path.join(HOME, rel)))
    hits = du_many([p for _, p in found])
    if hits:
        lookup = dict((os.path.normpath(p), l) for l, p in found)
        total_bytes = 0
        for size, path in hits:
            total_bytes += size
            label = lookup.get(os.path.normpath(path), os.path.basename(path))
            print(f"  {human(size):>9}  {label}")
            print(f"             {path}")
        print(f"\n  Total reclaimable: {human(total_bytes)}")
    else:
        print("  No cleanable items found")

    # ---- 6. Protected paths ----
    section("6. System-protected paths (rm fails with Operation not permitted; sudo is useless)")
    any_prot = False
    for rel in PROTECTED:
        p = os.path.join(HOME, rel)
        if access_error(p) == "EPERM":
            print(f"  [protected] {rel}")
            any_prot = True
    if not any_prot:
        print("  None detected (Full Disk Access may be granted, or paths absent)")
    print("\n  Note: CloudKit holds iCloud sync metadata; deleting it triggers a full")
    print("        re-sync. Even when deletable, it should not be deleted. Skip these.")

    # ---- 7. Off-limits ----
    section("7. Off-limits (corrupts apps or loses data)")
    for rel in FORBIDDEN:
        p = os.path.join(HOME, rel)
        if os.path.lexists(p):
            sz = du_many([p])
            size = human(sz[0][0]) if sz else "?"
            print(f"  {size:>9}  {rel}")
    print("\n  Chat history / phone backups / Docker disk images: clean in-app only.")

    # ---- 8. Next steps ----
    section("8. Next steps")
    print("  1) Grade items against references/cleanup-catalog.md")
    print("  2) Confirm relevant apps have quit (match full main-binary paths)")
    print("  3) Delete item by item with immediate verification; prefer Trash")
    print("  4) Empty the Trash, then verify with diskutil -- never with df")
    print()


if __name__ == "__main__":
    sys.exit(main())
