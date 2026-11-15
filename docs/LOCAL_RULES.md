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
