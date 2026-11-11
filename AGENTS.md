# Development and continuity

Read `docs/SESSION_HANDOFF.md` before resuming. Update it after meaningful changes with source changes, checks actually performed, deployment state, and remaining work. Keep source/documentation checkpoints backed up to this GitHub repository as requested by the user.

On the original device, also follow `/var/jb/var/mobile/AGENTS.md` and `.claude/CLAUDE.md` under that workspace. The shared workspace handoff remains `/var/jb/var/mobile/SESSION_HANDOFF.md`; keep its repository copy current.

Repository sources: `Tweak.x`, `daemon/collector.py`, `daemon/dashboard.py`. On-device working copies are `appmon-tweak/Tweak.x` and `appmon/` under the mobile workspace. Reconcile changes deliberately.

Tests: `/var/jb/usr/local/bin/python3.14 -m unittest discover -s daemon/tests -v`. Build: `make package` with Theos at `/var/theos`. Distinguish building from installing. `make install` may respring the device.

Never commit credentials, captured activity, databases, private logs, or conversation transcripts.
