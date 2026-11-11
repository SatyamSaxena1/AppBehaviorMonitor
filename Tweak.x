/*
 * AppBehaviorMonitor — MobileSubstrate tweak
 * Hooks network, file, keychain, clipboard, location, camera/mic, tracking.
 * Sends JSON events via Unix datagram socket (fire-and-forget).
 */

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <CoreLocation/CoreLocation.h>
#import <AVFoundation/AVFoundation.h>
#import <Security/Security.h>
#import <substrate.h>
#import <sys/socket.h>
#import <sys/un.h>
#import <dlfcn.h>
#import <mach-o/dyld.h>

#define SOCK_PATH "/var/jb/var/mobile/Documents/appmon/appmon.sock"
#define MAX_MSG_SIZE 4096
#define RATE_LIMIT_PER_SEC 100

// ─── Globals ─────────────────────────────────────────────

static int g_sock = -1;
static struct sockaddr_un g_addr;
static NSString *g_appId = nil;
static NSString *g_exeName = nil;

// Rate limiting: per-category token bucket
static NSMutableDictionary<NSString *, NSNumber *> *g_rateCounts;
static NSMutableDictionary<NSString *, NSNumber *> *g_rateTimestamps;
static dispatch_queue_t g_rateQueue;

// ─── IPC ─────────────────────────────────────────────────

static void setupSocket(void) {
    g_sock = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (g_sock < 0) return;

    // Non-blocking
    int flags = fcntl(g_sock, F_GETFL, 0);
    fcntl(g_sock, F_SETFL, flags | O_NONBLOCK);

    memset(&g_addr, 0, sizeof(g_addr));
    g_addr.sun_family = AF_UNIX;
    strncpy(g_addr.sun_path, SOCK_PATH, sizeof(g_addr.sun_path) - 1);
}

static BOOL rateLimitOK(NSString *category) {
    __block BOOL ok = NO;
    dispatch_sync(g_rateQueue, ^{
        NSTimeInterval now = [[NSDate date] timeIntervalSince1970];
        NSNumber *ts = g_rateTimestamps[category];
        NSNumber *count = g_rateCounts[category];

        if (!ts || (now - ts.doubleValue) >= 1.0) {
            g_rateTimestamps[category] = @(now);
            g_rateCounts[category] = @(1);
            ok = YES;
        } else if (count.integerValue < RATE_LIMIT_PER_SEC) {
            g_rateCounts[category] = @(count.integerValue + 1);
            ok = YES;
        }
    });
    return ok;
}

static void sendEvent(NSString *category, NSString *action, NSString *detail, NSDictionary *extra) {
    if (g_sock < 0) return;
    if (!rateLimitOK(category)) return;

    NSMutableDictionary *evt = [NSMutableDictionary dictionary];
    evt[@"ts"] = @([[NSDate date] timeIntervalSince1970]);
    evt[@"pid"] = @(getpid());
    evt[@"app"] = g_appId ?: @"unknown";
    evt[@"exe"] = g_exeName ?: @"unknown";
    evt[@"cat"] = category;
    evt[@"act"] = action;
    if (detail) evt[@"detail"] = detail;
    if (extra) {
        NSData *ej = [NSJSONSerialization dataWithJSONObject:extra options:0 error:nil];
        if (ej) evt[@"extra"] = [[NSString alloc] initWithData:ej encoding:NSUTF8StringEncoding];
    }

    NSData *json = [NSJSONSerialization dataWithJSONObject:evt options:0 error:nil];
    if (!json || json.length > MAX_MSG_SIZE) return;

    sendto(g_sock, json.bytes, json.length, MSG_DONTWAIT,
           (struct sockaddr *)&g_addr, sizeof(g_addr));
}

// ─── Network Hooks (NSURLSession) ────────────────────────

static NSString *requestSummary(NSURLRequest *req) {
    return [NSString stringWithFormat:@"%@ %@", req.HTTPMethod ?: @"GET", req.URL.absoluteString ?: @"?"];
}

%hook NSURLSession

- (NSURLSessionDataTask *)dataTaskWithRequest:(NSURLRequest *)request completionHandler:(id)handler {
    sendEvent(@"network", @"data_task", requestSummary(request), @{
        @"host": request.URL.host ?: @"",
        @"scheme": request.URL.scheme ?: @""
    });
    return %orig;
}

- (NSURLSessionUploadTask *)uploadTaskWithRequest:(NSURLRequest *)request fromData:(NSData *)bodyData completionHandler:(id)handler {
    sendEvent(@"network", @"upload_task", requestSummary(request), @{
        @"host": request.URL.host ?: @"",
        @"bytes": @(bodyData.length)
    });
    return %orig;
}

- (NSURLSessionDownloadTask *)downloadTaskWithRequest:(NSURLRequest *)request completionHandler:(id)handler {
    sendEvent(@"network", @"download_task", requestSummary(request), @{
        @"host": request.URL.host ?: @""
    });
    return %orig;
}

%end

// ─── File System Hooks ───────────────────────────────────

static BOOL isInterestingPath(NSString *path) {
    if (!path) return NO;
    static NSArray *prefixes = nil;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        prefixes = @[
            @"/var/mobile/Library/",
            @"/var/mobile/Documents/",
            @"/var/mobile/Containers/",
            @"/private/var/mobile/",
            @"/var/Keychains/",
            @"/var/preferences/",
            @"/var/db/",
        ];
    });
    for (NSString *p in prefixes) {
        if ([path hasPrefix:p]) return YES;
    }
    return NO;
}

%hook NSFileManager

- (NSData *)contentsAtPath:(NSString *)path {
    if (isInterestingPath(path)) {
        sendEvent(@"file", @"read", path, nil);
    }
    return %orig;
}

- (BOOL)createFileAtPath:(NSString *)path contents:(NSData *)data attributes:(NSDictionary *)attr {
    if (isInterestingPath(path)) {
        sendEvent(@"file", @"write", path, @{@"bytes": @(data.length)});
    }
    return %orig;
}

- (BOOL)removeItemAtPath:(NSString *)path error:(NSError **)error {
    if (isInterestingPath(path)) {
        sendEvent(@"file", @"delete", path, nil);
    }
    return %orig;
}

- (BOOL)copyItemAtPath:(NSString *)src toPath:(NSString *)dst error:(NSError **)error {
    if (isInterestingPath(src) || isInterestingPath(dst)) {
        sendEvent(@"file", @"copy", [NSString stringWithFormat:@"%@ -> %@", src, dst], nil);
    }
    return %orig;
}

%end

// ─── Clipboard Hooks ─────────────────────────────────────

%hook UIPasteboard

- (void)setString:(NSString *)string {
    NSString *preview = string.length > 100 ? [string substringToIndex:100] : string;
    sendEvent(@"clipboard", @"set_string", preview, @{@"length": @(string.length)});
    %orig;
}

- (NSString *)string {
    NSString *val = %orig;
    if (val) {
        NSString *preview = val.length > 100 ? [val substringToIndex:100] : val;
        sendEvent(@"clipboard", @"get_string", preview, @{@"length": @(val.length)});
    }
    return val;
}

- (void)setStrings:(NSArray<NSString *> *)strings {
    sendEvent(@"clipboard", @"set_strings", nil, @{@"count": @(strings.count)});
    %orig;
}

- (void)setImage:(UIImage *)image {
    sendEvent(@"clipboard", @"set_image", nil, @{
        @"w": @(image.size.width), @"h": @(image.size.height)
    });
    %orig;
}

%end

// ─── Location Hooks ──────────────────────────────────────

%hook CLLocationManager

- (void)startUpdatingLocation {
    sendEvent(@"location", @"start_updating", nil, nil);
    %orig;
}

- (void)startMonitoringSignificantLocationChanges {
    sendEvent(@"location", @"start_significant", nil, nil);
    %orig;
}

- (void)requestWhenInUseAuthorization {
    sendEvent(@"location", @"req_when_in_use", nil, nil);
    %orig;
}

- (void)requestAlwaysAuthorization {
    sendEvent(@"location", @"req_always", nil, nil);
    %orig;
}

%end

// ─── Camera / Mic Hooks ──────────────────────────────────

%hook AVCaptureSession

- (void)startRunning {
    // Determine inputs
    NSMutableArray *types = [NSMutableArray array];
    for (AVCaptureInput *input in self.inputs) {
        if ([input isKindOfClass:[AVCaptureDeviceInput class]]) {
            AVCaptureDevice *dev = [(AVCaptureDeviceInput *)input device];
            if ([dev hasMediaType:AVMediaTypeVideo]) [types addObject:@"video"];
            if ([dev hasMediaType:AVMediaTypeAudio]) [types addObject:@"audio"];
        }
    }
    NSString *cat = [types containsObject:@"audio"] ? @"mic" : @"camera";
    sendEvent(cat, @"capture_start", [types componentsJoinedByString:@","], nil);
    %orig;
}

%end

%hook AVCaptureDevice

+ (void)requestAccessForMediaType:(AVMediaType)mediaType completionHandler:(void (^)(BOOL))handler {
    NSString *cat = [mediaType isEqualToString:AVMediaTypeAudio] ? @"mic" : @"camera";
    sendEvent(cat, @"request_access", (NSString *)mediaType, nil);
    %orig;
}

%end

// ─── Tracking Hooks ──────────────────────────────────────

%hook UIDevice

- (NSUUID *)identifierForVendor {
    sendEvent(@"tracking", @"identifierForVendor", nil, nil);
    return %orig;
}

%end

// ─── Keychain Hooks (C functions via MSHookFunction) ─────

static NSString *keychainService(CFDictionaryRef dict) {
    if (!dict) return nil;
    NSDictionary *d = (__bridge NSDictionary *)dict;
    id svc = d[(__bridge id)kSecAttrService];
    return [svc isKindOfClass:[NSString class]] ? svc : nil;
}

static OSStatus (*orig_SecItemCopyMatching)(CFDictionaryRef query, CFTypeRef *result);
static OSStatus hooked_SecItemCopyMatching(CFDictionaryRef query, CFTypeRef *result) {
    sendEvent(@"keychain", @"copy_matching", keychainService(query), nil);
    return orig_SecItemCopyMatching(query, result);
}

static OSStatus (*orig_SecItemAdd)(CFDictionaryRef attributes, CFTypeRef *result);
static OSStatus hooked_SecItemAdd(CFDictionaryRef attributes, CFTypeRef *result) {
    sendEvent(@"keychain", @"add", keychainService(attributes), nil);
    return orig_SecItemAdd(attributes, result);
}

static OSStatus (*orig_SecItemUpdate)(CFDictionaryRef query, CFDictionaryRef attributesToUpdate);
static OSStatus hooked_SecItemUpdate(CFDictionaryRef query, CFDictionaryRef attributesToUpdate) {
    sendEvent(@"keychain", @"update", keychainService(query), nil);
    return orig_SecItemUpdate(query, attributesToUpdate);
}

static OSStatus (*orig_SecItemDelete)(CFDictionaryRef query);
static OSStatus hooked_SecItemDelete(CFDictionaryRef query) {
    sendEvent(@"keychain", @"delete", keychainService(query), nil);
    return orig_SecItemDelete(query);
}

// ─── ATTrackingManager (weak-linked) ─────────────────────

%hook ATTrackingManager

+ (void)requestTrackingAuthorizationWithCompletionHandler:(void (^)(NSUInteger))handler {
    sendEvent(@"tracking", @"req_att_authorization", nil, nil);
    %orig;
}

+ (NSUInteger)trackingAuthorizationStatus {
    sendEvent(@"tracking", @"check_att_status", nil, nil);
    return (NSUInteger)%orig;
}

%end

// ─── ASIdentifierManager ─────────────────────────────────

%hook ASIdentifierManager

- (NSUUID *)advertisingIdentifier {
    sendEvent(@"tracking", @"advertisingIdentifier", nil, nil);
    return %orig;
}

%end

// ─── Constructor ─────────────────────────────────────────

%ctor {
    @autoreleasepool {
        // Identify app
        g_appId = [[NSBundle mainBundle] bundleIdentifier] ?: @"unknown";
        g_exeName = [[[NSProcessInfo processInfo] processName] copy] ?: @"unknown";

        // Rate limiting
        g_rateCounts = [NSMutableDictionary dictionary];
        g_rateTimestamps = [NSMutableDictionary dictionary];
        g_rateQueue = dispatch_queue_create("com.appmon.rate", DISPATCH_QUEUE_SERIAL);

        // Socket
        setupSocket();

        // Hook keychain C functions
        MSHookFunction((void *)SecItemCopyMatching, (void *)hooked_SecItemCopyMatching, (void **)&orig_SecItemCopyMatching);
        MSHookFunction((void *)SecItemAdd, (void *)hooked_SecItemAdd, (void **)&orig_SecItemAdd);
        MSHookFunction((void *)SecItemUpdate, (void *)hooked_SecItemUpdate, (void **)&orig_SecItemUpdate);
        MSHookFunction((void *)SecItemDelete, (void *)hooked_SecItemDelete, (void **)&orig_SecItemDelete);
    }
}
