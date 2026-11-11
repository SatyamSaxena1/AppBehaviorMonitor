#import <UIKit/UIKit.h>
#import "MCPSetupController.h"
#import "InsightsUI.h"

static NSDictionary *Categories(void) {
    return @{@"network": @[@"Internet", @"network"], @"file": @[@"Files", @"folder"],
             @"keychain": @[@"Saved passwords", @"key.fill"], @"clipboard": @[@"Clipboard", @"doc.on.clipboard"],
             @"location": @[@"Location", @"location.fill"], @"camera": @[@"Camera", @"camera.fill"],
             @"mic": @[@"Microphone", @"mic.fill"], @"tracking": @[@"Tracking", @"scope"]};
}
static NSString *Name(NSDictionary *row) {
    for (NSString *key in @[@"display_name", @"exe_name", @"app_id"]) {
        id value = row[key];
        if ([value isKindOfClass:NSString.class] && [value length] && ![value isEqual:@"unknown"]) return value;
    }
    return @"Unknown app";
}
static NSString *Action(NSDictionary *row) {
    NSDictionary *labels = @{@"data_task": @"Sent a request", @"upload_task": @"Uploaded data", @"download_task": @"Downloaded data",
        @"read": @"Read a file", @"write": @"Saved a file", @"delete": @"Deleted a file", @"copy": @"Copied a file",
        @"copy_matching": @"Read saved credentials", @"add": @"Saved credentials", @"update": @"Updated credentials",
        @"get_string": @"Read the clipboard", @"set_string": @"Copied text", @"set_strings": @"Copied items", @"set_image": @"Copied an image",
        @"start_updating": @"Started location updates", @"start_significant": @"Started location monitoring",
        @"req_when_in_use": @"Requested location access", @"req_always": @"Requested background location",
        @"capture_start": @"Started capture", @"request_access": @"Requested permission",
        @"identifierForVendor": @"Read device identifier", @"advertisingIdentifier": @"Read advertising identifier",
        @"req_att_authorization": @"Requested tracking permission", @"check_att_status": @"Checked tracking permission"};
    NSString *action = row[@"action"] ?: @"Activity";
    return labels[action] ?: [[action stringByReplacingOccurrencesOfString:@"_" withString:@" "] capitalizedString];
}
static NSString *Age(id timestamp) {
    if (![timestamp respondsToSelector:@selector(doubleValue)]) return @"No activity yet";
    NSTimeInterval delta = MAX(0, NSDate.date.timeIntervalSince1970 - [timestamp doubleValue]);
    if (delta < 60) return @"Just now";
    if (delta < 3600) return [NSString stringWithFormat:@"%.0fm ago", floor(delta / 60)];
    if (delta < 86400) return [NSString stringWithFormat:@"%.0fh ago", floor(delta / 3600)];
    return [NSString stringWithFormat:@"%.0fd ago", floor(delta / 86400)];
}

@interface MonitorController : UITableViewController <UISearchResultsUpdating>
@property BOOL apps;
@property BOOL help;
@property NSString *appID;
@property NSArray *rows;
@property NSDictionary *health;
@property NSString *connection;
@property NSURLSessionDataTask *task;
@property NSTimer *timer;
@property UISearchController *search;
@end

@implementation MonitorController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.rows = @[];
    self.connection = @"Connecting to this iPhone…";
    self.tableView.backgroundColor = UIColor.systemGroupedBackgroundColor;
    self.tableView.rowHeight = UITableViewAutomaticDimension;
    self.tableView.estimatedRowHeight = 78;
    if (self.help) { self.title = @"About & Setup"; return; }
    self.title = self.appID ? self.title : self.apps ? @"Your Apps" : @"Activity";
    self.refreshControl = [UIRefreshControl new];
    [self.refreshControl addTarget:self action:@selector(refresh) forControlEvents:UIControlEventValueChanged];
    self.search = [[UISearchController alloc] initWithSearchResultsController:nil];
    self.search.searchResultsUpdater = self;
    self.search.obscuresBackgroundDuringPresentation = NO;
    self.search.searchBar.placeholder = self.apps ? @"Find an observed app" : @"Search recent activity";
    self.navigationItem.searchController = self.search;
    self.definesPresentationContext = YES;
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(becameActive) name:UIApplicationDidBecomeActiveNotification object:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(stopPolling) name:UIApplicationDidEnterBackgroundNotification object:nil];
}
- (void)viewDidAppear:(BOOL)animated { [super viewDidAppear:animated]; if (!self.help) [self becameActive]; }
- (void)viewWillDisappear:(BOOL)animated { [super viewWillDisappear:animated]; [self stopPolling]; }
- (void)becameActive {
    if (!self.view.window || self.help) return;
    [self refresh];
    [self stopPolling];
    self.timer = [NSTimer scheduledTimerWithTimeInterval:5 target:self selector:@selector(refresh) userInfo:nil repeats:YES];
}
- (void)stopPolling { [self.timer invalidate]; self.timer = nil; }
- (void)dealloc { [[NSNotificationCenter defaultCenter] removeObserver:self]; [self.task cancel]; }
- (void)updateSearchResultsForSearchController:(UISearchController *)controller { [self.tableView reloadData]; }
- (NSArray *)visibleRows {
    NSString *query = self.search.searchBar.text.lowercaseString;
    if (!query.length) return self.rows;
    return [self.rows filteredArrayUsingPredicate:[NSPredicate predicateWithBlock:^BOOL(NSDictionary *row, NSDictionary *bindings) {
        NSString *text = [NSString stringWithFormat:@"%@ %@ %@ %@", Name(row), row[@"app_id"], row[@"detail"] ?: @"", Action(row)];
        return [text.lowercaseString containsString:query];
    }]];
}
- (void)refresh {
    if (self.task) return;
    NSString *path = self.apps ? @"/api/apps" : @"/api/events?limit=200";
    if (self.appID) {
        NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"];
        path = [path stringByAppendingFormat:@"&app=%@", [self.appID stringByAddingPercentEncodingWithAllowedCharacters:allowed]];
    }
    NSURL *url = [NSURL URLWithString:[@"http://127.0.0.1:8800" stringByAppendingString:path]];
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:8];
    __weak typeof(self) weakSelf = self;
    self.task = [NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        id result = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        BOOL ok = !error && [(NSHTTPURLResponse *)response statusCode] == 200 && [result isKindOfClass:NSArray.class];
        dispatch_async(dispatch_get_main_queue(), ^{
            MonitorController *self = weakSelf;
            if (!self) return;
            self.task = nil;
            [self.refreshControl endRefreshing];
            if (ok) {
                self.rows = result;
                self.connection = @"Connected · Stored on this iPhone";
            } else self.connection = @"Collector unavailable · Pull to retry";
            [self.tableView reloadData];
        });
    }];
    [self.task resume];
}
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return self.help ? 4 : 2; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    if (self.help) return 1;
    if (section == 0) return 1;
    return MAX(1, self.visibleRows.count);
}
- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    if (self.help) return @[@"Welcome home", @"Get activity flowing", @"Control which apps are monitored", @"Understand your history"][section];
    return section == 0 ? @"PRIVACY MONITOR" : self.apps ? @"Observed apps" : @"Latest 200 events";
}
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    if (!self.help && section == 1) return @"Recorded actions are observations, not proof of misuse. Only apps and actions supported by the tweak appear here.";
    return nil;
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.textLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
    cell.textLabel.numberOfLines = 0;
    cell.detailTextLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline];
    cell.detailTextLabel.numberOfLines = 0;
    cell.detailTextLabel.textColor = UIColor.secondaryLabelColor;
    cell.textLabel.adjustsFontForContentSizeCategory = YES;
    cell.detailTextLabel.adjustsFontForContentSizeCategory = YES;
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    if (self.help) {
        NSArray *texts = @[@"A native view of the activity collected on your iPhone. Pull down to refresh; lists update automatically while visible. Your history stays with the local collector.",
          @"Install AppBehaviorMonitor using Sileo or Zebra. Close and reopen apps after updating the tweak. If the collector is unavailable after a reboot, reactivate your jailbreak and check its service.",
          @"In Choicy, open an app’s tweak configuration and disable AppBehaviorMonitor to exclude it. Close and reopen the app afterward. This is useful for sensitive apps or troubleshooting instability.",
          @"Events are kept for seven days with hourly cleanup while the collector runs. Search covers the loaded list. Tap an event for original details. The monitor cannot see every action, and an event does not mean an app is malicious."];
        cell.textLabel.text = texts[indexPath.section];
        cell.textLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
        return cell;
    }
    if (indexPath.section == 0) {
        cell.textLabel.text = self.connection;
        cell.imageView.image = [UIImage systemImageNamed:[self.connection hasPrefix:@"Connected"] ? @"checkmark.shield.fill" : @"exclamationmark.triangle"];
        cell.imageView.tintColor = [self.connection hasPrefix:@"Connected"] ? UIColor.systemTealColor : UIColor.systemOrangeColor;
        cell.detailTextLabel.text = self.apps ? [NSString stringWithFormat:@"%lu apps observed · Pull down to refresh", (unsigned long)self.rows.count] : @"Updates every 5 seconds while you’re here";
        return cell;
    }
    NSArray *rows = self.visibleRows;
    if (!rows.count) {
        cell.textLabel.text = self.search.searchBar.text.length ? @"No matches in this list" : @"No activity yet";
        cell.detailTextLabel.text = @"Use another app, then come back. Check Setup if nothing appears.";
        return cell;
    }
    NSDictionary *row = rows[indexPath.row];
    cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
    cell.selectionStyle = UITableViewCellSelectionStyleDefault;
    cell.imageView.tintColor = UIColor.systemTealColor;
    if (self.apps) {
        cell.textLabel.text = Name(row);
        cell.detailTextLabel.text = [NSString stringWithFormat:@"%@ events · %@", row[@"event_count"] ?: @0, Age(row[@"last_seen"])];
        cell.imageView.image = [UIImage systemImageNamed:@"app.dashed"];
    } else {
        NSArray *category = Categories()[row[@"category"]] ?: @[@"Activity", @"circle"];
        cell.textLabel.text = self.appID ? Action(row) : Name(row);
        cell.detailTextLabel.text = [NSString stringWithFormat:@"%@ · %@\n%@", category[0], Age(row[@"timestamp"]), Action(row)];
        cell.imageView.image = [UIImage systemImageNamed:category[1]];
    }
    return cell;
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    if (self.help || indexPath.section == 0 || !self.visibleRows.count) return;
    NSDictionary *row = self.visibleRows[indexPath.row];
    if (self.apps) {
        MonitorController *detail = [[MonitorController alloc] initWithStyle:UITableViewStyleInsetGrouped];
        detail.appID = row[@"app_id"];
        detail.title = Name(row);
        [self.navigationController pushViewController:detail animated:YES];
    } else {
        NSString *detail = [NSString stringWithFormat:@"%@\n%@\n\n%@\n\n%@", Name(row), row[@"app_id"], row[@"detail"] == NSNull.null ? @"No additional details" : row[@"detail"] ?: @"No additional details", row[@"extra_json"] == NSNull.null ? @"" : row[@"extra_json"] ?: @""];
        UIAlertController *alert = [UIAlertController alertControllerWithTitle:Action(row) message:detail preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"Done" style:UIAlertActionStyleCancel handler:nil]];
        [self presentViewController:alert animated:YES completion:nil];
    }
}
@end

UIViewController *PMActivityScreen(BOOL apps) {
    MonitorController *screen = [[MonitorController alloc] initWithStyle:UITableViewStyleInsetGrouped];
    screen.apps = apps;
    return screen;
}

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (nonatomic, strong) UIWindow *window;
@end
@implementation AppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(developerChanged) name:@"PMDeveloperModeChanged" object:nil];
    [self configureTabs:NO];
    [self.window makeKeyAndVisible];
    return YES;
}
- (void)developerChanged { [self configureTabs:YES]; }
- (void)configureTabs:(BOOL)settings {
    BOOL developer = [NSUserDefaults.standardUserDefaults boolForKey:@"PMDeveloperMode"];
    NSMutableArray *screens = [NSMutableArray arrayWithArray:@[[PMHomeController new], [PMInsightsController new]]];
    NSMutableArray *titles = [NSMutableArray arrayWithArray:@[@"Overview", @"Insights"]];
    NSMutableArray *icons = [NSMutableArray arrayWithArray:@[@"house.fill", @"sparkles"]];
    if (developer) {
        [screens addObject:[[PMDeveloperController alloc] initWithStyle:UITableViewStyleInsetGrouped]];
        [titles addObject:@"Developer"]; [icons addObject:@"wrench.and.screwdriver"];
    }
    [screens addObject:[[PMSettingsController alloc] initWithStyle:UITableViewStyleInsetGrouped]];
    [titles addObject:@"Settings"]; [icons addObject:@"gearshape.fill"];
    NSMutableArray *navigation = [NSMutableArray new];
    for (NSUInteger i=0;i<screens.count;i++) {
        UINavigationController *nav = [[UINavigationController alloc] initWithRootViewController:screens[i]];
        nav.navigationBar.prefersLargeTitles = YES;
        nav.tabBarItem = [[UITabBarItem alloc] initWithTitle:titles[i] image:[UIImage systemImageNamed:icons[i]] tag:i];
        [navigation addObject:nav];
    }
    UITabBarController *tabs = [UITabBarController new]; tabs.viewControllers = navigation;
    tabs.view.tintColor = UIColor.systemOrangeColor;
    if (settings) tabs.selectedIndex = navigation.count-1;
    self.window.rootViewController = tabs;
}
@end
int main(int argc, char *argv[]) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(AppDelegate.class)); }
}
