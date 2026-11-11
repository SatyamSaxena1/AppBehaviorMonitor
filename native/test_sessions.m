#import "PMSessions.h"
static NSDictionary *Item(double t, NSString *author) { return @{@"created_at":@(t),@"author":author}; }
int main(void) { @autoreleasepool {
    NSCAssert(Sessions(@[]).count == 0,@"empty history");
    NSArray *groups = Sessions(@[Item(100,@"A"),Item(5000,@"A"),Item(5100,@"A"),Item(5200,@"B")]);
    NSCAssert(groups.count == 3,@"author and time boundaries");
    NSCAssert([groups[1] count] == 2,@"nearby reviews grouped");
    NSCAssert([groups[0][0][@"created_at"] intValue] == 5200,@"newest first");
    NSCAssert(Sessions(@[Item(100,@"A"),Item(1900,@"A")]).count == 1,@"inclusive boundary");
    NSCAssert(Sessions(@[Item(100,@"A"),Item(1901,@"A")]).count == 2,@"gap starts history");
    puts("Session grouping checks passed");
} return 0; }
