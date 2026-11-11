# Privacy Monitor AI connector

A local, read-only MCP server for Claude/Codex-compatible stdio clients.
Tools: `activity_summary`, `recent_activity`, and `contacted_domains`.
No arbitrary SQL, shell commands, settings changes, or automatic uploads.
Time windows are bounded to seven days and results are capped. Clipboard contents,
raw file paths, complete URLs, query strings, and credential details are omitted.
When an AI client calls tools, returned metadata enters that client's conversation
and is subject to its data handling; the connector cannot promise it stays on-device.

## On the iPhone

The Sileo collector package installs this command:

```
/var/jb/usr/libexec/privacy-monitor/launch-mcp
```

For development before upgrading the collector, use the absolute path to
`privacy-monitor-ai/server/launch` in this checkout. It chooses an installed Python
and serves JSON-RPC on stdin/stdout; it does not open a TCP port.

Claude Code registration (supported CLI):

```
claude mcp add --transport stdio privacy-monitor -- /var/jb/bin/sh /var/jb/usr/libexec/privacy-monitor/launch-mcp
```

Codex registration:

```
codex mcp add privacy-monitor -- /var/jb/bin/sh /var/jb/usr/libexec/privacy-monitor/launch-mcp
```

A new client session may be needed to load tools. Registration and actual client
availability must be verified separately; protocol tests alone do not prove a chat
has loaded the connector.

## From a computer

Use an SSH stdio command to run the installed launcher on the phone. Set up your
own key-based SSH access first. Example MCP client configuration:

```json
{"mcpServers":{"privacy-monitor":{"command":"ssh","args":["-T","-o","BatchMode=yes","mobile@YOUR_IPHONE_IP","/var/jb/bin/sh","/var/jb/usr/libexec/privacy-monitor/launch-mcp"]}}}
```

Replace the address; do not embed a root password. SSH needs access to the phone,
while database reads run as mobile. Do not expose the local HTTP dashboard directly
to the internet. A browser-only/mobile-cloud AI client cannot launch this stdio
server without a separate supported bridge; none is provisioned here.

The portable local plugin is this directory (plugin.json, mcp.json, skills/, server/,
and assets/). It runs on the jailbroken device, not on arbitrary desktop systems
without SSH. No cloud plugin publication is included.

## Verification

Four isolated tests cover protocol initialization/discovery/calls, bounded argument
validation, missing-database behavior, and metadata redaction. The packaged collector
smoke test also ingests a synthetic event and queries its domain over stdio.

Launch through the explicit /var/jb/bin/sh interpreter; direct exec of a new shell script was rejected by iOS on the development device. Tool discovery through the explicit interpreter was verified.
