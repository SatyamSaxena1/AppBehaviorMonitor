#import <Foundation/Foundation.h>
static NSArray *Sessions(NSArray *items) {
    NSMutableArray *groups = [NSMutableArray new], *group = nil; NSDictionary *last = nil;
    NSArray *sorted = [items sortedArrayUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) { return [b[@"created_at"] compare:a[@"created_at"]]; }];
    for (NSDictionary *item in sorted) {
        if (!last || [last[@"created_at"] doubleValue]-[item[@"created_at"] doubleValue]>1800 || ![last[@"author"] isEqual:item[@"author"]]) { group = [NSMutableArray new]; [groups addObject:group]; }
        [group addObject:item]; last = item;
    }
    return groups;
}
