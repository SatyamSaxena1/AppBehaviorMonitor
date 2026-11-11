#!/usr/bin/env python3
"""Build three rootless beta packages and a flat Sileo repository; no installation."""
import argparse, datetime, email.utils, gzip, hashlib, json, os, plistlib, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.1~beta1'
URL = 'https://satyamsaxena1.github.io/repo/'
ENV = dict(os.environ, PATH='/var/jb/usr/local/bin:/var/jb/usr/bin:/var/jb/bin:/usr/sbin:/usr/bin:/bin', LC_ALL='C')
DPKG = '/var/jb/usr/bin/dpkg-deb'

def run(*args):
    return subprocess.run([str(x) for x in args], env=ENV, check=True, capture_output=True, text=True).stdout

def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)

def package(stage, name, description, depends, output):
    control = f'Package: {name}\nName: {description}\nVersion: {VERSION}\nArchitecture: iphoneos-arm64\nMaintainer: SatyamSaxena1\nAuthor: SatyamSaxena1\nSection: Utilities\nDepends: {depends}\nHomepage: {URL}\nDescription: {description} for Dopamine rootless. Public beta.\n'
    write(stage/'DEBIAN/control', control)
    target = output/f'{name}_{VERSION}_iphoneos-arm64.deb'
    print(run(DPKG, '--root-owner-group', '-b', stage, target).strip())
    return target

def build(output):
    output.mkdir(parents=True, exist_ok=True)
    debs = output/'debs'
    debs.mkdir(exist_ok=True)
    work = ROOT/'distribution/build'
    if work.exists(): shutil.rmtree(work)
    work.mkdir(parents=True)

    # Reproducible signed native app from tracked source, with release dependency metadata.
    print(run('/var/jb/usr/local/bin/python3.14', ROOT/'native/build.py').strip())
    native = work/'native'
    run(DPKG, '-R', ROOT/'native/build/PrivacyMonitor-App.deb', native)
    infofile = native/'var/jb/Applications/PrivacyMonitor.app/Info.plist'
    info = plistlib.loads(infofile.read_bytes())
    info['CFBundleShortVersionString'] = '1.0.1'
    info['CFBundleVersion'] = '2'
    infofile.write_bytes(plistlib.dumps(info))
    # Info.plist is part of the signed app; re-sign after changing it.
    run('/var/jb/usr/bin/ldid', '-S', infofile.parent/'PrivacyMonitor')
    native_deb = package(native, 'com.appmon.native', 'Privacy Monitor',
                         f'com.appmon.tweak (>= {VERSION}), com.appmon.collector (>= {VERSION})', debs)

    # Compile the actual engine sources through Theos; never package runtime data.
    print(run('/var/jb/usr/bin/make', '-C', ROOT, 'FINALPACKAGE=1', f'PACKAGE_VERSION={VERSION}', 'package')[-1600:])
    built = ROOT/'packages'/f'com.appmon.tweak_{VERSION}_iphoneos-arm64.deb'
    if not built.exists():
        candidates = list((ROOT/'packages').glob('com.appmon.tweak_*.deb'))
        built = max(candidates, key=lambda p: p.stat().st_mtime)
    tweak = work/'tweak'
    run(DPKG, '-R', built, tweak)
    engine_deb = package(tweak, 'com.appmon.tweak', 'Privacy Monitor Engine',
                         f'mobilesubstrate, com.appmon.collector (>= {VERSION})', debs)

    collector = work/'collector'
    libexec = collector/'var/jb/usr/libexec/privacy-monitor'
    libexec.mkdir(parents=True)
    for file in ['collector.py', 'dashboard.py']:
        shutil.copy2(ROOT/'daemon'/file, libexec/file)
    for file in ['mcp_server.py', 'launch']:
        target = 'launch-mcp' if file == 'launch' else file
        shutil.copy2(ROOT/'privacy-monitor-ai/server'/file, libexec/target)
    write(libexec/'launch', '''#!/var/jb/bin/sh
set -eu
umask 077
for python in /var/jb/usr/bin/python3 /var/jb/usr/local/bin/python3 /var/jb/usr/local/bin/python3.14; do
    if [ -x "$python" ] && "$python" -c 'import sqlite3, http.server' 2>/dev/null; then
        exec "$python" /var/jb/usr/libexec/privacy-monitor/collector.py
    fi
done
printf '%s\n' 'Privacy Monitor requires Python 3 with sqlite3. Reinstall its Python dependency in Sileo.' >&2
exit 1
''', 0o755)
    plist = dict(Label='com.appmon.collector', ProgramArguments=['/var/jb/bin/sh', '/var/jb/usr/libexec/privacy-monitor/launch'],
                 RunAtLoad=True, KeepAlive=True, UserName='mobile',
                 WorkingDirectory='/var/jb/usr/libexec/privacy-monitor',
                 StandardErrorPath='/var/jb/var/mobile/Documents/appmon/collector.log',
                 StandardOutPath='/var/jb/var/mobile/Documents/appmon/collector.log', ThrottleInterval=10)
    plistpath = collector/'var/jb/Library/LaunchDaemons/com.appmon.collector.plist'
    plistpath.parent.mkdir(parents=True)
    plistpath.write_bytes(plistlib.dumps(plist))
    stop = '''#!/var/jb/bin/sh
set -e
/var/jb/usr/bin/launchctl bootout system/com.appmon.collector >/dev/null 2>&1 || true
exit 0
'''
    write(collector/'DEBIAN/preinst', stop, 0o755)
    write(collector/'DEBIAN/prerm', stop, 0o755)
    write(collector/'DEBIAN/postinst', '''#!/var/jb/bin/sh
set -eu
runtime=/var/jb/var/mobile/Documents/appmon
mkdir -p "$runtime"
chown mobile:mobile "$runtime"
chmod 755 "$runtime"
for file in "$runtime"/appmon.db* "$runtime"/*.log; do
    if [ -f "$file" ]; then
        chown mobile:mobile "$file"
        chmod 600 "$file"
    fi
done
touch "$runtime/collector.log"
chown mobile:mobile "$runtime/collector.log"
chmod 600 "$runtime/collector.log"
/var/jb/usr/bin/launchctl bootstrap system /var/jb/Library/LaunchDaemons/com.appmon.collector.plist
exit 0
''', 0o755)
    collector_deb = package(collector, 'com.appmon.collector', 'Privacy Monitor Collector',
                            'python3 (>= 3.9) | xyz.cypwn.python314 (>= 3.14)', debs)

    shutil.copy2(ROOT/'assets/privacy-monitor-icon.png', output/'icon.png')
    shutil.copy2(ROOT/'assets/privacy-monitor-icon.png', output/'privacy-monitor-icon.png')
    for name in ['CydiaIcon.png', 'CydiaIcon@2x.png', 'CydiaIcon@3x.png']:
        shutil.copy2(output/'icon.png', output/name)
    entries=[]
    assets=[]
    for file in [native_deb, engine_deb, collector_deb]:
        payload=file.read_bytes()
        fields=run(DPKG, '-f', file).strip()
        relative=file.relative_to(output).as_posix()
        entries.append(fields+'\n'+f'Filename: {relative}\nSize: {len(payload)}\nMD5sum: {hashlib.md5(payload).hexdigest()}\nSHA256: {hashlib.sha256(payload).hexdigest()}\nSHA512: {hashlib.sha512(payload).hexdigest()}\nDepiction: {URL}\nSileoDepiction: {URL}depiction.json\nIcon: {URL}privacy-monitor-icon.png\n')
        assets.append(dict(file=relative, sha256=hashlib.sha256(payload).hexdigest(), size=len(payload)))
    data=('\n'.join(entries)+'\n').encode()
    (output/'Packages').write_bytes(data)
    (output/'Packages.gz').write_bytes(gzip.compress(data, mtime=0))
    lines=['Origin: Satyam Saxena', 'Label: Privacy Monitor Beta', 'Icon: '+URL+'privacy-monitor-icon.png', 'Suite: stable', 'Version: 1.0',
           'Codename: privacy-monitor', 'Architectures: iphoneos-arm64', 'Components: main',
           'Description: Privacy Monitor for Dopamine rootless iOS 15. Public beta.',
           'Date: '+email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc),usegmt=True)]
    for key,algorithm in [('MD5Sum','md5'),('SHA256','sha256'),('SHA512','sha512')]:
        lines.append(key+':')
        for filename in ['Packages','Packages.gz']:
            blob=(output/filename).read_bytes()
            lines.append(f' {hashlib.new(algorithm,blob).hexdigest()} {len(blob)} {filename}')
    write(output/'Release', '\n'.join(lines)+'\n')
    depiction={'class':'DepictionTabView','minVersion':'0.1','tabs':[{'class':'DepictionStackView','tabname':'Details','views':[
      {'class':'DepictionHeaderView','title':'Privacy Monitor · Beta'},
      {'class':'DepictionSubheaderView','title':'See what apps do on your iPhone.'},
      {'class':'DepictionMarkdownView','markdown':'Native app, activity collector, and monitoring engine. Install **Privacy Monitor** to get all three.\n\n**Compatibility:** Dopamine rootless; tested engine on iPhone 13 Pro Max / iOS 15.5. Native app launch and clean-device installation are still awaiting beta verification. Other devices are unverified.\n\n**After installing:** restart apps to load the engine; use the package manager’s Restart SpringBoard action if needed. In Choicy, exclude apps that become unstable.\n\nHistory stays on the phone and is retained for seven days. Supported hooks are observations, not proof of misuse. The optional AI connector is read-only and requires a separate client connection.\n\n[Source and issues](https://github.com/SatyamSaxena1/AppBehaviorMonitor)'}]}]}
    write(output/'depiction.json',json.dumps(depiction,indent=2)+'\n')
    write(output/'manifest.json',json.dumps(dict(version=VERSION,packages=assets),indent=2)+'\n')
    write(output/'index.html','''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Privacy Monitor · Jailbreak Repo</title>
<style>body{max-width:660px;margin:12vh auto;padding:24px;background:#fff0dc;color:#351d12;font:18px/1.65 system-ui}img{width:90px;border-radius:22px}a{color:#9e371c}.button{display:inline-block;padding:12px 20px;border:1px solid #b36a42;border-radius:12px;margin:8px 8px 8px 0}code{overflow-wrap:anywhere}small{color:#70503d}</style>
<img src="icon.png" alt="Privacy Monitor shield"><h1>Your apps. A clearer view.</h1><p><a href="../privacy-monitor/">Read the project story →</a></p><p>Privacy Monitor is a native activity viewer for jailbroken iPhones. Explore app timelines, network activity, and supported privacy-sensitive actions.</p>
<p><a class="button" href="sileo://source/https://satyamsaxena1.github.io/repo/">Add to Sileo</a><a class="button" href="zbra://sources/add/https://satyamsaxena1.github.io/repo/">Add to Zebra</a></p>
<p>Or add this source manually:<br><code>https://satyamsaxena1.github.io/repo/</code></p><h2>Install Privacy Monitor</h2><p>Sileo installs the native app, engine, collector, and Python dependency together. Reopen apps after installation so the engine can load. Use Choicy to exclude sensitive or unstable apps.</p>
<h2>Public beta</h2><p>For Dopamine rootless. The engine has been tested on iPhone 13 Pro Max with iOS 15.5. Native app launch and installation on a clean device are not yet verified; other devices and jailbreak types are unverified.</p><p>Recorded activity is not a verdict that an app is malicious. History stays on your device and is retained for seven days. Uninstalling preserves history.</p>
<p><a href="https://github.com/SatyamSaxena1/AppBehaviorMonitor">Source, support &amp; issues</a> · <a href="manifest.json">Package checksums</a></p><small>Beta repository. Package indexes are currently unsigned; downloads have SHA-256 checksums. No accounts or hosted activity collection.</small></html>''')
    validate(output)

def validate(output):
    release_fields = dict(line.split(':', 1) for line in (output/'Release').read_text().splitlines() if line and not line.startswith(' '))
    assert release_fields.get('Components', '').strip(), 'Sileo requires Components in Release'
    assert 'iphoneos-arm64' in release_fields.get('Architectures', '').split(), 'Missing rootless architecture'
    paragraphs=(output/'Packages').read_text().strip().split('\n\n')
    found=set()
    for entry in paragraphs:
        fields=dict(line.split(': ',1) for line in entry.splitlines() if ': ' in line and not line.startswith(' '))
        packagefile=output/fields['Filename']
        assert packagefile.is_relative_to(output) and packagefile.is_file()
        blob=packagefile.read_bytes()
        assert len(blob)==int(fields['Size'])
        assert hashlib.sha256(blob).hexdigest()==fields['SHA256']
        found.add(fields['Package'])
        listing=run(DPKG,'-c',packagefile)
        assert './var/jb/' in listing and './usr/' not in listing
        control=run(DPKG,'-f',packagefile)
        assert f'Version: {VERSION}' in control and 'Architecture: iphoneos-arm64' in control
    assert found=={'com.appmon.native','com.appmon.tweak','com.appmon.collector'}
    assert gzip.decompress((output/'Packages.gz').read_bytes())==(output/'Packages').read_bytes()
    for script in (ROOT/'distribution/build').glob('*/DEBIAN/*'):
        if script.name!='control': run('/var/jb/bin/sh','-n',script)
    print('Validated three packages, rootless paths, versions, checksums, compressed index, and maintainer shell syntax.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    options=parser.parse_args()
    build(options.output.resolve())
