# Shared Claude / Codex handoff

Last updated: 2026-11-12 (Asia/Kolkata), by Codex.

## User intent and instructions

The user asked Codex to resume Claude's device sessions, inherit its custom instructions and environment knowledge, and leave documentation so Claude can resume as needed.

Read `AGENTS.md`, `CLAUDE.md`, and `.claude/CLAUDE.md`. The latter is the original device protocol and includes the separate PaprLab project context; it has been read and preserved unchanged. Its statement that PaprLab is the active project predates the latest Privacy Monitor work.

## Current project: Privacy Monitor / AppBehaviorMonitor

Goal: show app activity on this personal jailbroken iPhone in plain language, with recognizable app names rather than bundle IDs, technical action codes, and raw paths.

Architecture: Theos Objective-C/Logos tweak in UIKit processes sends JSON events over a nonblocking Unix datagram socket to a Python collector. The collector batches writes into SQLite and serves a local Safari dashboard at `http://127.0.0.1:8800/`.

Paths:
- `appmon-tweak/`: working tweak source, Makefile, package output.
- `appmon/collector.py` and `appmon/dashboard.py`: working daemon/dashboard source.
- `appmon-repo/`: separate Git repository with earlier copies under `daemon/`; do not assume it matches the working sources or copy it over newer files.
- `Documents/appmon/`: runtime database, socket, and logs.
- Current socket in both working sources: `/var/jb/var/mobile/Documents/appmon/appmon.sock`.
- Installed tweak: `/var/jb/Library/MobileSubstrate/DynamicLibraries/AppBehaviorMonitor.dylib`.
- Existing launch plist: `/var/jb/Library/LaunchDaemons/com.appmon.collector.plist`.
- Theos: `/var/theos`, confirmed present.

The original plan `.claude/plans/deep-singing-frog.md` is useful background but contains obsolete paths and intended behavior that must be checked against source. In particular, its `/var/jb/var/run/appmon.sock` was replaced because that directory is root-owned.

## Recovered stopping point

Latest substantive Claude session: `2852b26c-e865-4495-b425-c10e29966fd7` (slug `deep-singing-frog`). Full transcript is under `.claude/projects/*/2852b26c-e865-4495-b425-c10e29966fd7.jsonl`. The sessions index omits newer sessions; use transcript files and history rather than trusting it alone.

The user asked for a friendlier dashboard and a todo list, then said they installed what was needed. Claude reported rewriting the dashboard and restarting the collector, and began adding real app display names. It stopped at its usage limit immediately after editing the overview SQL query to select `display_name`.

Source facts checked by Codex:
- `appmon-tweak/Tweak.x` defines `g_displayName`, obtains `CFBundleDisplayName` / `CFBundleName` / executable fallback, and sends it as JSON `name`.
- `appmon/collector.py` defines the `display_name` column, migration for older DBs, and batch insert of JSON `name`.
- `appmon/dashboard.py` prefers `display_name` in `friendly_app_name`; event rows, overview, and per-app handling have changes.
- Overview SQL includes `display_name`.
- `/api/apps` query still selects app ID and executable without `display_name`; review whether it and live rendering/search need completion.
- Source overview aggregation groups by app ID; check whether older events with empty names can obscure newer names.
- Installed dylib timestamp predates the latest tweak source edits. No rebuild/install of the display-name changes has been verified.
- LaunchDaemon plist exists, but loaded state and current collector version have not been verified.

Claude discussed AltList and Choicy. Its implemented name lookup uses NSBundle directly; do not describe an AltList integration as implemented. Choicy exclusion help, icons, and other proposed features also require source verification before claiming completion.

## Pending tasks recovered from Claude

Original task records: `.claude/tasks/2852b26c-e865-4495-b425-c10e29966fd7/`.

1. Verify dashboard rendering in mobile Safari.
2. Verify live feed with real app activity and friendly labels.
3. Verify per-app views and category filters.
4. Verify search by app name, website, and action.
5. Verify device stability after tweak activation.
6. Set up / verify LaunchDaemon auto-start.

All six were pending in Claude's task files. Historical task commands are not a reliable runbook; resolve tools and use current permissions. Do not copy embedded credentials into docs or commands.

## Next development steps

1. Read applicable project instructions; inspect current diffs in working directories and `appmon-repo` without overwriting either copy.
2. Resolve Python's actual executable path. The original device instructions note a nonstandard Python 3.14 package location; `python3` is not on the current executor PATH.
3. Finish reviewing real-name propagation through dashboard queries, API, live feed, and search.
4. Run focused Python syntax and temporary-database checks, including migration of an older schema and a synthetic named event.
5. Build the tweak using `appmon-tweak/Makefile`; record artifact and results.
6. Check collector process and LaunchDaemon state before restarting or installing; perform deployment only under current permissions and authorization. The Makefile's `after-install` runs `sbreload`, which interrupts the UI.
7. Verify real events and UI behavior, then reconcile newer working sources into the Git repository deliberately.

## Codex work completed in this handoff session

Read Claude's device protocols, original plan, recent conversation, task records, working Makefile, collector schema/insert, and relevant dashboard/tweak lines. Created workspace `AGENTS.md`, `CLAUDE.md`, and this shared handoff. No application source edits, builds, installs, restarts, resprings, or runtime tests were performed by Codex in this session.

For Claude: read this file and continue from the next development steps. For Codex: use the same record and update it as work progresses. Keep completed work, unresolved failures, and unverified deployment state explicit.

## Development checkpoint: 2026-11-12, Codex

The user authorized continuing the pending work and backing up progress to GitHub. Keep making source/documentation checkpoints in `SatyamSaxena1/AppBehaviorMonitor`; never include credentials, runtime event databases, private logs, or session transcripts.

Completed:
- Updated `appmon/dashboard.py`: live feed uses display names and escapes event text, app-list API includes names, overview/API choose the latest nonempty name even when newer events lack one, per-app lookup uses latest names, search matches display names and friendly action labels. App routes decode URL-encoded identifiers.
- Added `appmon/tests/test_dashboard.py`: four passing isolated tests covering old-schema migration, ingestion, mixed named/unnamed event history, app summaries, name/action searches, routes, and filters. Live JavaScript integration is checked at the served-source level; actual Safari execution is still pending.
- Python executable confirmed: `/var/jb/usr/local/bin/python3.14` (3.14.3).
- Python syntax checks passed. Run tests with `/var/jb/usr/local/bin/python3.14 -m unittest discover -s appmon/tests -v` (or `daemon/tests` in the Git repository).
- `make -C appmon-tweak package` succeeded: `appmon-tweak/packages/com.appmon.tweak_1.0.0-2+debug_iphoneos-arm64.deb`. Build emitted locale warnings and a missing sysctl warning; exit status was zero.
- LaunchDaemon confirmed loaded in system domain, running as mobile, with KeepAlive and RunAtLoad. Sent SIGTERM to its mobile-owned collector process; launchd restarted it (PID 48783 -> 51954). Updated collector/dashboard are now loaded.
- Live HTTP checks returned 200 for overview, live page, search, apps API, events API, and stats API; checked live-page display-name integration and API display_name fields without printing private events.
- GitHub CLI authenticated as SatyamSaxena1; repository remote is https://github.com/SatyamSaxena1/AppBehaviorMonitor.git, branch master.

Still pending:
- Install the rebuilt tweak: noninteractive sudo requires a password, and this executor cannot write the root-owned install locations under current filesystem permissions. No install or respring performed. Do not reuse credentials found in historical tasks.
- After installation, newly started app processes must load the new dylib before they emit names. Test real named events, Safari layout/live JavaScript behavior, and device stability.
- LaunchDaemon auto-start configuration is verified, but survival across an actual respring/reboot was not tested.

Repository checkpoint includes the newer working tweak and Python sources, regression tests, and portable handoff documentation. Build output is reproducible and is not committed.

GitHub backup confirmed: commit `29cbdf7` pushed to `origin/master`, including source, tests, and handoff notes. Git's configured shell-based gh credential helper cannot execute on this device. Push succeeded using a temporary Python GIT_ASKPASS executable that obtained the existing gh token in memory; no token was written to the repository or printed. Future pushes may need the same workaround until the device's Git shell/helper configuration is repaired.

## Installation verified after user installation

User reported installing the package through the device UI. Codex confirmed via dpkg-query: `com.appmon.tweak` is `install ok installed`, version `1.0.0-2+debug`. Read-only database checks found 52 events carrying nonempty display names; the app-list API included display names for three apps. Overview, live page, apps API, and stats API all returned HTTP 200. This verifies installed version and real display-name ingestion; Safari visual layout and extended device stability still need observation. No respring or installation was performed by Codex.
