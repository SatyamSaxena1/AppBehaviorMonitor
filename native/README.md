# Privacy Monitor — native jailbreak companion

A UIKit application for the existing AppBehaviorMonitor collector. Apps, Activity, and Setup tabs use native navigation, large titles, system dark/light colors, Dynamic Type, SF Symbols, search, and pull-to-refresh. Activity shows the latest 200 events; app selection opens that app's timeline. An event opens its recorded details. Refreshes run every five seconds while visible and stop in the background. Failed requests retain the previous list and show collector unavailability.

## Build on this device

```sh
/var/jb/usr/local/bin/python3.14 native/build.py
```

Requires clang, ldid, dpkg-deb, and `/var/theos/sdks/iPhoneOS15.6.sdk`. The script builds arm64 for iOS 15+, signs the executable, creates icons and a manifest, and packages a rootless application under `/var/jb/Applications/PrivacyMonitor.app`. Output: `native/build/PrivacyMonitor-App.deb` (ignored by Git).

## Install

Requires the existing `com.appmon.tweak` package **and a running collector on 127.0.0.1:8800**. The native package is a companion; it does not install or replace the collector. Install the deb using Sileo/Zebra. The post-install script runs uicache to register the Home Screen icon. No respring is requested by this package.

On the development device, a copy is available at `/var/tmp/PrivacyMonitor-App.deb`. The collector also serves a copy from `appmon/static/PrivacyMonitor-App.deb` at `http://127.0.0.1:8800/download/app`. Download in Safari, open its download list, and share the package to Sileo.

## Verification status

Compiled and signed on-device; verified arm64 Mach-O, code signature load command, plist, and rootless Debian package contents. Native UI launch/interaction requires installing the package and has not yet been tested. Confirm app launch, dark/light appearance, large text, pull-to-refresh, app timeline navigation, search, event details, and background/foreground refresh behavior after installation.
