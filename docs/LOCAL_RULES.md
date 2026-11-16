# Local activity summaries — 1.2

Replaces AI/MCP following user feedback: too much text, stale reviews, wants custom logic.

The read-only activity endpoint computes exact counts over the selected 1h/24h/7d
window under the collector DB lock. All aggregates and history use the same range,
exclude future events and com.appmon.native, and require no AI calls. App names use
the latest nonempty recorded display name in the window. No raw content is returned.

Four explicit rule counters: clipboard/get_string, camera or mic/capture_start,
location/start_updating or start_significant, tracking/advertisingIdentifier.
Permission requests and identifierForVendor do not count as capture or advertising
ID calls. Counts describe API calls, not successful capture/transmission, ongoing
access, or malicious behavior. Zero does not establish safety. Categories still
show every supported recorded action (including permission requests).

Charts: ring segments show category shares of total actions; category bars scale to
the largest count in that section. History bars scale to peak bucket. Windows are
rolling durations. Seven-day history uses seven 24-hour buckets; timestamps are
formatted locally, not claimed to be calendar-day totals. No old review alerts.

Freshness: refresh on appearance, foreground, pull, and every five seconds while
visible. HTTP cache bypassed. Generated-at and last-event timestamps are separate;
a working collector can have no recent events. Failed refreshes keep an explicitly
stale snapshot. No events gives an empty state. No fake live/camera indicator.

Retired MCP: new packages omit protocol/plugin code and replace launch-mcp with a
failing retirement stub. Old collector package files disappear on upgrade. Existing
review table is not served/created; older records age out via legacy retention.
The source-path launcher also fails for stale CLI registrations. Local privacy-monitor
entries are removed from Claude/Codex config; restart clients to drop cached tools.
Previous release artifacts/source remain in Git history. No data database is committed.

## Sandboxed app delivery — beta3

Instagram investigation: installed beta2, engine mapped in the live process, Choicy injection enabled, zero recorded Instagram events. Read-only sandbox_check for Instagram returned network-outbound denied (1/errno 0) for the Unix socket path, versus allowed (0) for the diagnostic process; file-write-data was allowed. Only jailbreak/unsandboxed apps had recorded activity. No private app files/content were inspected. Socket enumeration showed active network connections, without capturing their payload.

Engine now uses nonblocking IPv4 UDP to 127.0.0.1:8801 when Unix delivery fails; permission-denied failures select the fallback for the process lifetime. It preserves errno, avoids sender recursion, and retains the existing rate limits. Collector binds only loopback, accepts bounded JSON objects, rejects malformed/oversized input, and caps pending batches. Both IPC transports are best-effort local telemetry, not authenticated evidence; any local process able to send to them can spoof metadata. No listener is bound to external interfaces.

Network coverage additionally includes connect/connectx attempts (IP/port/result) and getaddrinfo lookups (host/result). Counts are API-call observations and can overlap at multiple layers; they are not unique requests, packets, successful transmissions, or proof of tracking. Custom direct syscalls/other stacks can still bypass hooks.

Constructor/foreground sends monitor/loaded metadata, stored only in monitoring_status with seven-day retention. Apps can show engine-seen with zero recorded calls; it is not a fake activity event or a claim the process is currently running. Actual app_count/total/category/history aggregates exclude status. Last-event query now excludes future timestamps consistently.

Checks: 15 backend tests, isolated Unix+UDP packaged collector smoke with malformed datagrams and separate status, native IPC harness compiled from actual Tweak.x source (simulated Unix EPERM -> real UDP, cached fallback, errno preservation, recursion guard), full native/engine build and package validation. New Instagram behavior requires installing beta3 and restarting Instagram; not yet verified in Instagram itself.
