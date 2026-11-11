# Privacy Monitor — Insights-first jailbreak app

Release 1.1 opens on Overview, AI Insights, and Settings. Reviews are saved by a
connected AI when the user requests analysis; the app does not run a background
model or create fake findings. Empty and connection-error states explain what to do.

Each review separates observations, interpretation, practical recommendations,
confidence/limitations, time window, and cited event evidence. Client-provided author
labels are displayed as labels, not verified identities. Evidence snapshots contain
only bounded event metadata and safe domain names, never raw clipboard/path/URL/
credential details. Reviews expire seven days after creation.

Settings → Developer Mode is off by default. Enabling it adds a Developer tab with
app diagnostics, raw activity feed, MCP configuration/copy/share tools, and local web
dashboard. Technical IDs/actions appear in evidence details only in Developer Mode.
The normal app refreshes on appearance/pull-to-refresh; raw developer views retain
visible-only polling. The generated artwork is bundled for the overview.

## Build and install

Use `distribution/build_repo.py` to build/sign the native app, engine, and collector
packages with consistent versions. The builder requires clang, ldid, dpkg-deb,
Theos, and `/var/theos/sdks/iPhoneOS15.6.sdk`. Target: rootless arm64, iOS 15+.
Install/update Privacy Monitor from https://satyamsaxena1.github.io/repo/ in Sileo.
The collector dependency supplies `/api/insights` and stores reviews alongside events.
No privileged installation is performed by the build script.

## AI connection

Developer → MCP connection setup provides on-device Claude Code/Codex commands,
MCP JSON, and validated SSH configuration for computer clients. Copy/share prepares
configuration; it never executes a command or uploads history. In normal mode,
Ask for a review shares a plain-language request for the user to send to an assistant.
See `../privacy-monitor-ai/README.md` for tool capabilities and data handling.

## Verification limits

Native Objective-C builds and signs on this device. Migration, MCP read/write,
evidence validation, idempotent retries, redaction, retention, and HTTP read-back
are tested with isolated databases. Actual installed UI layout, Dynamic Type,
VoiceOver, share flows, developer-mode switching, and fresh root installation still
need device observation; no automated native UI runner is available here.
