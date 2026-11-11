# Sileo repository distribution

Host: `https://satyamsaxena1.github.io/repo/`, from the `repo/` directory of
`SatyamSaxena1/SatyamSaxena1.github.io` on branch `main`. The portfolio root is unchanged.

## Packages

- `com.appmon.native`: native app; depends on engine and collector.
- `com.appmon.tweak`: signed rootless engine; depends on collector and MobileSubstrate.
- `com.appmon.collector`: Python sources, rootless launch wrapper, LaunchDaemon, and optional read-only MCP stdio server. Depends on Procursus Python 3.9+ or the existing CyPwn Python 3.14 package.

Collector installation registers a mobile-user service under the existing
`com.appmon.collector` label, replacing a manually installed service on upgrades.
It stores runtime history under `/var/jb/var/mobile/Documents/appmon`, preserves
history on upgrade/removal, and uses restrictive file permissions for database/logs.
Python files install under `/var/jb/usr/libexec/privacy-monitor` rather than a developer workspace.
The collector's maintainer scripts manage launchd; they are not run by the builder.

## Build and verify

```sh
/var/jb/usr/local/bin/python3.14 distribution/build_repo.py --output ../portfolio-site/repo
/var/jb/usr/local/bin/python3.14 distribution/test_packages.py
/var/jb/usr/local/bin/python3.14 -m unittest discover -s daemon/tests -v
/var/jb/usr/local/bin/python3.14 -m unittest discover -s privacy-monitor-ai/server -v
```

Run from the AppBehaviorMonitor repository. Requires Theos and iPhoneOS15.6 SDK,
clang, ldid, make, and dpkg-deb. The builder stages only tracked program sources;
no captured activity, credentials, or development logs are packaged.

The output contains three debs, Packages/Packages.gz, a Release file with
checksums, a Sileo depiction, icon, download manifest, and landing page.
The repository is currently unsigned; the page states this. Package integrity
is verified against generated checksums. Add signing/key distribution in a later
release rather than claiming these indexes have an authenticated signature.

## Publish updates

1. Bump VERSION in build_repo.py. Never change a published deb under the same version.
2. Build and run tests. Test installation/upgrade on a suitable jailbreak device.
3. Commit source and handoff in AppBehaviorMonitor.
4. Commit only repo/ in the portfolio repository, push main, and wait for Pages.
5. Verify the public Release and Packages files, then download every referenced
   deb and compare its size and SHA-256 with manifest.json.

Current release is explicitly a beta. Engine testing: iPhone 13 Pro Max/iOS 15.5.
The extracted collector has passed isolated startup, socket ingestion, HTTP, MCP,
and shutdown checks. APT simulation resolves the three packages on the development
device. Actual clean-device root installation, native UI launch, and other iOS/jailbreak
combinations remain unverified; source compatibility is not a claim of testing.

The MCP connector is optional and does not start a network listener or upload data.
See ../privacy-monitor-ai/README.md to connect a local/SSH stdio client.
