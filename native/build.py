#!/var/jb/usr/local/bin/python3.14
"""Build a signed rootless UIKit companion package on the jailbroken device."""
from pathlib import Path
import os, plistlib, shutil, subprocess, struct, zlib

root = Path(__file__).resolve().parent
stage = root / 'build' / 'package'
if stage.exists():
    shutil.rmtree(stage)
app = stage / 'var/jb/Applications/PrivacyMonitor.app'
app.mkdir(parents=True)
sdk = Path('/var/theos/sdks/iPhoneOS15.6.sdk')
env = dict(os.environ, PATH='/var/jb/usr/bin:/var/jb/bin:/usr/bin:/bin', LC_ALL='C')
subprocess.run(['/var/jb/usr/bin/clang', '-isysroot', str(sdk), '-target', 'arm64-apple-ios15.0',
                '-fobjc-arc', '-fmodules', '-Wall', '-Wextra', '-Wno-unused-parameter',
                '-framework', 'UIKit', '-framework', 'Foundation',
                str(root / 'main.m'), '-o', str(app / 'PrivacyMonitor')], check=True, env=env)
subprocess.run(['/var/jb/usr/bin/ldid', '-S', str(app / 'PrivacyMonitor')], check=True, env=env)
info = dict(CFBundleIdentifier='com.appmon.native', CFBundleName='Privacy Monitor',
            CFBundleDisplayName='Privacy Monitor', CFBundleExecutable='PrivacyMonitor',
            CFBundlePackageType='APPL', CFBundleShortVersionString='1.0.0', CFBundleVersion='1',
            MinimumOSVersion='15.0', UIDeviceFamily=[1, 2], LSRequiresIPhoneOS=True,
            UILaunchScreen={}, UISupportedInterfaceOrientations=['UIInterfaceOrientationPortrait',
            'UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight'],
            NSAppTransportSecurity=dict(NSAllowsArbitraryLoads=True),
            CFBundleIcons=dict(CFBundlePrimaryIcon=dict(CFBundleIconFiles=['AppIcon60x60'], UIPrerenderedIcon=True)))
(app / 'Info.plist').write_bytes(plistlib.dumps(info))
# Generate a local shield icon with no image dependencies.
def inside(x, y, poly):
    result = False
    j = len(poly)-1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj-xi)*(y-yi)/(yj-yi)+xi):
            result = not result
        j = i
    return result

def icon(size):
    rows=[]
    outer=[(.5,.16),(.79,.27),(.75,.59),(.65,.75),(.5,.86),(.35,.75),(.25,.59),(.21,.27)]
    inner=[(.5,.23),(.72,.32),(.68,.57),(.59,.70),(.5,.77),(.41,.70),(.32,.57),(.28,.32)]
    tick=[(.35,.48),(.40,.43),(.48,.52),(.64,.35),(.69,.40),(.48,.63)]
    for y in range(size):
        row=bytearray([0])
        for x in range(size):
            a,b=(x+.5)/size,(y+.5)/size
            color=(12+int(b*8),22+int(b*12),38+int(b*15))
            if inside(a,b,outer): color=(60,220,207)
            if inside(a,b,inner): color=(19,46,63)
            if inside(a,b,tick): color=(235,255,253)
            row.extend(color)
        rows.append(bytes(row))
    def chunk(kind,data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',size,size,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
for scale in (2,3):
    (app / f'AppIcon60x60@{scale}x.png').write_bytes(icon(60*scale))
control=stage/'DEBIAN'
control.mkdir()
(control/'control').write_text('''Package: com.appmon.native
Name: Privacy Monitor
Version: 1.0.0
Architecture: iphoneos-arm64
Description: Native companion for AppBehaviorMonitor with app timelines and local activity.
Maintainer: SatyamSaxena1
Author: SatyamSaxena1
Section: Applications
Depends: com.appmon.tweak
''')
for name, command in [('postinst', '/var/jb/usr/bin/uicache -p /var/jb/Applications/PrivacyMonitor.app'),
                      ('postrm', '/var/jb/usr/bin/uicache -u /var/jb/Applications/PrivacyMonitor.app')]:
    script=control/name
    script.write_text('#!/var/jb/bin/sh\nset -e\n'+command+'\n')
    script.chmod(0o755)
output=root/'build'/'PrivacyMonitor-App.deb'
subprocess.run(['/var/jb/usr/bin/dpkg-deb','--root-owner-group','-b',str(stage),str(output)],check=True,env=env)
print(output)
