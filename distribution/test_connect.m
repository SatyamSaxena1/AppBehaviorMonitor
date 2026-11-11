#import <Foundation/Foundation.h>
#import <JavaScriptCore/JavaScriptCore.h>
int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 3) return 2;
        JSContext *context = [JSContext new];
        for (int i=1; i<3; i++) {
            NSError *error;
            NSString *code = [NSString stringWithContentsOfFile:@(argv[i]) encoding:NSUTF8StringEncoding error:&error];
            if (!code) { fprintf(stderr, "%s\n", error.localizedDescription.UTF8String); return 1; }
            [context evaluateScript:code];
            if (context.exception) { fprintf(stderr, "%s\n", context.exception.toString.UTF8String); return 1; }
        }
        puts("MCP web configuration tests passed in iOS JavaScriptCore.");
    }
    return 0;
}
