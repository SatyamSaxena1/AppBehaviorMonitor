"""Compile the actual native IPC source; simulate denied Unix IPC, receive real localhost UDP."""
import json,os,socket,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'Tweak.x').read_text().split('// ─── Network Hooks')[0]
headers,body=source.split('#define SOCK_PATH',1)
headers=headers.replace('#import <substrate.h>','')+'\n#include <fcntl.h>\n#include <unistd.h>\n#include <string.h>\n'
shim=r"""
static int unixAttempts;
static ssize_t deniedUnixSend(int fd,const void *buffer,size_t size,int flags,const struct sockaddr *address,socklen_t length) {
    if(address->sa_family==AF_UNIX) { unixAttempts++;errno=EPERM;return -1; }
    return sendto(fd,buffer,size,flags,address,length);
}
#define sendto deniedUnixSend
"""
main=r"""
int main(int argc,char **argv) { @autoreleasepool {
    if(argc!=2)return 2;
    g_appId=@"fixture.nativefallback";g_exeName=@"Fixture";g_displayName=@"Fixture";
    g_rateCounts=[NSMutableDictionary new];g_rateTimestamps=[NSMutableDictionary new];
    g_rateQueue=dispatch_queue_create("fixture.rate",DISPATCH_QUEUE_SERIAL);
    setupSocket();g_udpAddr.sin_port=htons(atoi(argv[1]));
    errno=EAGAIN;sendEvent(@"monitor",@"loaded",nil,nil);
    if(errno!=EAGAIN || unixAttempts!=1 || !atomic_load(&g_preferUDP))return 3;
    sendEvent(@"network",@"dns_lookup",nil,@{@"host":@"example.test"});
    if(errno!=EAGAIN || unixAttempts!=1)return 4;
    g_sending=YES;sendEvent(@"network",@"dns_lookup",nil,nil);g_sending=NO;
    if(unixAttempts!=1)return 5;
    close(g_sock);close(g_udpSock);
}return 0;}
"""
with tempfile.TemporaryDirectory(dir='/var/jb/tmp') as temp:
    path=Path(temp);(path/'sender.m').write_text(headers+shim+'#define SOCK_PATH'+body+main)
    env=dict(os.environ,LC_ALL='C')
    subprocess.run(['/var/jb/usr/bin/clang','-isysroot','/var/theos/sdks/iPhoneOS15.6.sdk','-I/var/theos/vendor/include','-target','arm64-apple-ios15.0','-fobjc-arc','-framework','Foundation',str(path/'sender.m'),'-o',str(path/'sender')],env=env,check=True)
    subprocess.run(['/var/jb/usr/bin/ldid','-S',str(path/'sender')],check=True)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver:
        receiver.bind(('127.0.0.1',0));receiver.settimeout(3)
        subprocess.run([str(path/'sender'),str(receiver.getsockname()[1])],check=True)
        events=[json.loads(receiver.recv(4096)) for _ in range(2)]
        assert events[0]['cat']=='monitor' and events[1]['act']=='dns_lookup'
        assert all(e['app']=='fixture.nativefallback' for e in events)
print('Native IPC: denied Unix -> real UDP fallback, cached fallback, errno and recursion guard passed.')
