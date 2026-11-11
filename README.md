# AppBehaviorMonitor

System-wide app behavior monitor for jailbroken iOS (Dopamine, rootless). Hooks into every UIKit app to log network requests, file access, keychain usage, clipboard, location, camera/mic, and tracking — stores everything in SQLite with a local web dashboard.

## Architecture

```
┌─ Every app process ──────────────────────────┐
│  AppBehaviorMonitor.dylib (MobileSubstrate)  │
│  - Logos ObjC hooks + MSHookFunction for C   │
│  - Sends events via Unix datagram socket     │
└──────────────┬───────────────────────────────┘
               │ Unix datagram socket (fire+forget)
               ▼
┌─ Python 3.14 daemon ────────────────────────┐
│  collector.py + dashboard.py                 │
│  - SQLite writer (single writer, no contention)│
│  - Web dashboard on 127.0.0.1:8800           │
└──────────────────────────────────────────────┘
```

## What Gets Hooked

| Category | Hooks |
|----------|-------|
| Network | `NSURLSession` data/upload/download tasks |
| File | `NSFileManager` read/write/delete/copy (sensitive paths only) |
| Keychain | `SecItemCopyMatching`, `SecItemAdd`, `SecItemUpdate`, `SecItemDelete` |
| Clipboard | `UIPasteboard` get/set string, strings, image |
| Location | `CLLocationManager` start methods + auth requests |
| Camera/Mic | `AVCaptureSession startRunning`, `AVCaptureDevice requestAccess` |
| Tracking | `ATTrackingManager`, `ASIdentifierManager`, `UIDevice identifierForVendor` |

Rate-limited to 100 events/sec/category per process.

## Requirements

- Jailbroken iOS 15+ (Dopamine rootless)
- Theos (for building the tweak)
- Python 3.x (for the collector daemon)
- MobileSubstrate

## Build & Install

```bash
# Build tweak
cd /path/to/repo
export THEOS=/var/theos
make package

# Install tweak
sudo dpkg -i packages/*.deb

# Copy daemon files
cp daemon/collector.py daemon/dashboard.py /var/jb/var/mobile/appmon/

# Install LaunchDaemon
sudo cp launchdaemon/com.appmon.collector.plist /var/jb/Library/LaunchDaemons/

# Start collector
launchctl load /var/jb/Library/LaunchDaemons/com.appmon.collector.plist

# Respring to activate tweak
sbreload
```

## Dashboard

Open Safari to `http://127.0.0.1:8800/`

- `/` — Overview: top apps, category breakdown
- `/app/<id>` — Per-app timeline with category filters
- `/category/<cat>` — Cross-app view per category
- `/live` — Auto-refreshing live feed (3-sec polling)
- `/search?q=` — Text search
- `/api/events`, `/api/apps`, `/api/stats` — JSON API

## Uninstall

```bash
dpkg -r com.appmon.tweak
launchctl unload /var/jb/Library/LaunchDaemons/com.appmon.collector.plist
rm -rf /var/jb/var/mobile/appmon /var/jb/var/mobile/Documents/appmon
rm /var/jb/Library/LaunchDaemons/com.appmon.collector.plist
sbreload
```

## License

MIT

## Everyday use

Open `http://127.0.0.1:8800/` in Safari. The overview shows collector availability and the last recorded activity; no recent events does not necessarily mean collection is broken. Use **Help** for setup and Choicy guidance. Safari's **Share → Add to Home Screen** gives you a dashboard shortcut.

The dashboard uses no external icon fonts. **Live** updates every three seconds while visible, shows connection failures, and includes a manual refresh button. Timeline entries provide expandable technical details. Activity reflects supported hooks, not a complete security audit or a verdict that an app is malicious.

Health endpoint: `/api/health`. Regression checks: `python3 -m unittest discover -s daemon/tests -v` (on this device, use `/var/jb/usr/local/bin/python3.14`). Shared development state is in `docs/SESSION_HANDOFF.md`.

## Sileo distribution and optional AI analysis

The beta repository is hosted at **https://satyamsaxena1.github.io/repo/**.
Install **Privacy Monitor** from Sileo/Zebra to resolve the native app, engine,
collector service, and Python dependency. See [distribution notes](distribution/README.md)
for reproducible builds, compatibility limits, and release validation.

An optional [read-only MCP connector](privacy-monitor-ai/README.md) lets a connected
Claude/Codex client query activity summaries, recent metadata, and contacted domains.
It omits raw clipboard/path/URL/credential details and never uploads activity by itself.
