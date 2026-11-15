# Privacy Monitor native app

Version 1.2: Today (activity ring and rule counters), Apps (category breakdown per
app), History (seven rolling 24-hour buckets), Settings. Optional Developer Mode
shows the raw feed, app diagnostics, and local dashboard. MCP and AI reviews are
removed. Local summary requests bypass HTTP cache and refresh every five seconds
while visible. App/background transitions stop polling and cancel outstanding
requests; old responses cannot replace a newer range. Failed refreshes retain the
last snapshot with a stale label and timestamp. No activity is never shown as safe.

Build with distribution/build_repo.py using clang, ldid, dpkg-deb, Theos, and the
installed iPhoneOS15.6 SDK. Rootless arm64, iOS 15+. Update via Sileo; building does
not install. Actual UI layout, accessibility, and interactions need device checks.
