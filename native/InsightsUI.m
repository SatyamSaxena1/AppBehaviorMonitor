#import "InsightsUI.h"

static UIColor *Accent(void) { return [UIColor colorWithRed:.13 green:.59 blue:.54 alpha:1]; }
static UIColor *CatColor(NSString *key) {
    NSDictionary *colors = @{@"network":UIColor.systemTealColor, @"file":UIColor.systemIndigoColor,
      @"keychain":UIColor.systemOrangeColor, @"clipboard":UIColor.systemPinkColor,
      @"camera":UIColor.systemPurpleColor, @"mic":UIColor.systemBlueColor,
      @"location":UIColor.systemGreenColor, @"tracking":UIColor.systemYellowColor};
    return colors[key] ?: UIColor.systemGrayColor;
}
static NSString *Count(id n) {
    double value = [n doubleValue];
    if (value >= 1000000) return [NSString stringWithFormat:@"%.1fm",value/1000000];
    if (value >= 10000) return [NSString stringWithFormat:@"%.0fk",value/1000];
    if (value >= 1000) return [NSString stringWithFormat:@"%.1fk",value/1000];
    return [NSString stringWithFormat:@"%.0f",value];
}
static NSString *Age(id timestamp) {
    if (![timestamp respondsToSelector:@selector(doubleValue)]) return @"No events yet";
    double age = MAX(0,NSDate.date.timeIntervalSince1970-[timestamp doubleValue]);
    if (age < 10) return @"Just now";
    if (age < 60) return [NSString stringWithFormat:@"%.0fs ago",age];
    if (age < 3600) return [NSString stringWithFormat:@"%.0fm ago",floor(age/60)];
    if (age < 86400) return [NSString stringWithFormat:@"%.0fh ago",floor(age/3600)];
    return [NSString stringWithFormat:@"%.0fd ago",floor(age/86400)];
}
static UILabel *Text(NSString *text, UIFontTextStyle style, UIColor *color) {
    UILabel *label = [UILabel new]; label.text = text ?: @"";
    label.font = [UIFont preferredFontForTextStyle:style]; label.adjustsFontForContentSizeCategory = YES;
    label.numberOfLines = 0; label.textColor = color; return label;
}
static UIStackView *VStack(void) { UIStackView *v = [UIStackView new]; v.axis = UILayoutConstraintAxisVertical; v.spacing = 12; return v; }
static UIStackView *Row(void) { UIStackView *v = [UIStackView new]; v.axis = UILayoutConstraintAxisHorizontal; v.spacing = 12; v.alignment = UIStackViewAlignmentCenter; return v; }
static UIImageView *Symbol(NSString *name, UIColor *color) {
    UIImageView *v = [[UIImageView alloc] initWithImage:[UIImage systemImageNamed:name]];
    v.contentMode = UIViewContentModeScaleAspectFit; v.tintColor = color; v.isAccessibilityElement = NO;
    [v setContentHuggingPriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal]; [v.heightAnchor constraintEqualToConstant:28].active = YES; return v;
}

@interface PMRing : UIView
@property NSArray *categories;
@end
@implementation PMRing
- (void)drawRect:(CGRect)rect {
    CGFloat total = 0; for (NSDictionary *c in self.categories) total += [c[@"count"] doubleValue];
    CGPoint center = CGPointMake(CGRectGetMidX(rect),CGRectGetMidY(rect));
    CGFloat radius = MIN(rect.size.width,rect.size.height)/2-12;
    UIBezierPath *base = [UIBezierPath bezierPathWithArcCenter:center radius:radius startAngle:0 endAngle:M_PI*2 clockwise:YES];
    base.lineWidth = 16; [UIColor.tertiarySystemFillColor setStroke]; [base stroke];
    CGFloat angle = -M_PI_2;
    for (NSDictionary *c in self.categories) {
        CGFloat sweep = total ? [c[@"count"] doubleValue]/total*M_PI*2 : 0;
        UIBezierPath *arc = [UIBezierPath bezierPathWithArcCenter:center radius:radius startAngle:angle endAngle:angle+sweep clockwise:YES];
        arc.lineWidth = 16; [CatColor(c[@"id"]) setStroke]; [arc stroke]; angle += sweep;
    }
}
- (void)traitCollectionDidChange:(UITraitCollection *)previous { [super traitCollectionDidChange:previous]; [self setNeedsDisplay]; }
@end

@interface PMCardsController ()
@property UIScrollView *scroll;
@property UIStackView *stack;
@property UIRefreshControl *refresh;
@property UISegmentedControl *period;
@property NSDictionary *summary;
@property NSString *failure;
@property NSString *appID;
@property NSString *appName;
@property NSString *signalID;
@property NSInteger hours;
@property NSInteger generation;
@property NSURLSessionDataTask *task;
@property NSTimer *timer;
- (void)render;
- (void)load;
@end

@implementation PMCardsController
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor = UIColor.systemGroupedBackgroundColor;
    if (!self.hours) self.hours = [self isKindOfClass:PMHistoryController.class] ? 168 : 24;
    self.title = self.appName ?: ([self isKindOfClass:PMHomeController.class] ? @"Today" : [self isKindOfClass:PMHistoryController.class] ? @"History" : @"Apps");
    self.scroll = [UIScrollView new]; self.scroll.alwaysBounceVertical = YES; self.scroll.translatesAutoresizingMaskIntoConstraints = NO;
    self.stack = VStack(); self.stack.spacing = 18; self.stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.scroll]; [self.scroll addSubview:self.stack];
    [NSLayoutConstraint activateConstraints:@[
      [self.scroll.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor],
      [self.scroll.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor],
      [self.scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],
      [self.scroll.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
      [self.stack.leadingAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.leadingAnchor constant:18],
      [self.stack.trailingAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.trailingAnchor constant:-18],
      [self.stack.topAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.topAnchor constant:10],
      [self.stack.bottomAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.bottomAnchor constant:-28],
      [self.stack.widthAnchor constraintEqualToAnchor:self.scroll.frameLayoutGuide.widthAnchor constant:-36]]];
    self.refresh = [UIRefreshControl new]; [self.refresh addTarget:self action:@selector(load) forControlEvents:UIControlEventValueChanged]; self.scroll.refreshControl = self.refresh;
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(active) name:UIApplicationDidBecomeActiveNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(stop) name:UIApplicationDidEnterBackgroundNotification object:nil];
    [self render];
}
- (void)viewDidAppear:(BOOL)animated { [super viewDidAppear:animated]; [self active]; }
- (void)viewWillDisappear:(BOOL)animated { [super viewWillDisappear:animated]; [self stop]; }
- (void)active {
    if (!self.view.window || UIApplication.sharedApplication.applicationState != UIApplicationStateActive) return;
    [self.timer invalidate]; [self load];
    self.timer = [NSTimer scheduledTimerWithTimeInterval:5 target:self selector:@selector(load) userInfo:nil repeats:YES];
}
- (void)stop { [self.timer invalidate]; self.timer = nil; [self.task cancel]; self.task = nil; self.generation++; [self.refresh endRefreshing]; }
- (void)dealloc { [NSNotificationCenter.defaultCenter removeObserver:self]; [self.task cancel]; [self.timer invalidate]; }
- (void)rangeChanged:(UISegmentedControl *)control {
    self.hours = [@[@1,@24,@168][control.selectedSegmentIndex] integerValue];
    [self.task cancel]; self.task = nil; self.generation++; self.summary = nil; [self render]; [self load];
}
- (void)load {
    if (self.task) return;
    NSString *path = [NSString stringWithFormat:@"http://127.0.0.1:8800/api/activity?hours=%ld",(long)self.hours];
    if (self.appID) path = [path stringByAppendingFormat:@"&app=%@",[self.appID stringByAddingPercentEncodingWithAllowedCharacters:[NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"]]];
    NSURLRequest *request = [NSURLRequest requestWithURL:[NSURL URLWithString:path] cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:8];
    NSInteger generation = ++self.generation; __weak typeof(self) weakSelf = self;
    self.task = [NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        id json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        BOOL ok = !error && [(NSHTTPURLResponse *)response statusCode] == 200 && [json isKindOfClass:NSDictionary.class] && [json[@"categories"] isKindOfClass:NSArray.class];
        dispatch_async(dispatch_get_main_queue(), ^{
            PMCardsController *self = weakSelf; if (!self || generation != self.generation) return;
            self.task = nil; [self.refresh endRefreshing];
            if (ok) { self.summary = json; self.failure = nil; }
            else self.failure = [(NSHTTPURLResponse *)response statusCode] == 404 ? @"Update the collector in Sileo" : @"Collector unavailable";
            CGPoint offset = self.scroll.contentOffset; [self render];
            [self.view layoutIfNeeded]; self.scroll.contentOffset = CGPointMake(0,MIN(offset.y,MAX(0,self.scroll.contentSize.height-self.scroll.bounds.size.height)));
        });
    }]; [self.task resume];
}
- (UIStackView *)card {
    UIStackView *v = VStack(); v.backgroundColor = UIColor.secondarySystemGroupedBackgroundColor;
    v.layer.cornerRadius = 24; v.layoutMargins = UIEdgeInsetsMake(20,20,20,20); v.layoutMarginsRelativeArrangement = YES; [self.stack addArrangedSubview:v]; return v;
}
- (void)button:(NSString *)title in:(UIStackView *)stack action:(void (^)(void))action {
    UIButton *b = [UIButton buttonWithType:UIButtonTypeSystem]; UIButtonConfiguration *c = [UIButtonConfiguration tintedButtonConfiguration];
    c.title = title; c.baseForegroundColor = Accent(); c.cornerStyle = UIButtonConfigurationCornerStyleLarge;
    c.contentInsets = NSDirectionalEdgeInsetsMake(12,12,12,12); b.configuration = c; b.titleLabel.numberOfLines = 0;
    [b addAction:[UIAction actionWithHandler:^(__kindof UIAction *a) { action(); }] forControlEvents:UIControlEventTouchUpInside]; [stack addArrangedSubview:b];
}
- (void)ring:(UIStackView *)card {
    PMRing *ring = [PMRing new]; ring.categories = self.summary[@"categories"] ?: @[]; ring.backgroundColor = UIColor.clearColor;
    [ring.heightAnchor constraintEqualToConstant:210].active = YES;
    UIStackView *center = VStack(); center.alignment = UIStackViewAlignmentCenter; center.spacing = 2; center.translatesAutoresizingMaskIntoConstraints = NO; [ring addSubview:center];
    UILabel *value = Text(Count(self.summary[@"total"]),UIFontTextStyleLargeTitle,UIColor.labelColor);
    value.accessibilityLabel = [NSString stringWithFormat:@"%@ recorded actions",self.summary[@"total"] ?: @0];
    [center addArrangedSubview:value]; [center addArrangedSubview:Text(@"recorded actions",UIFontTextStyleCaption1,UIColor.secondaryLabelColor)];
    [NSLayoutConstraint activateConstraints:@[[center.centerXAnchor constraintEqualToAnchor:ring.centerXAnchor],[center.centerYAnchor constraintEqualToAnchor:ring.centerYAnchor],[center.widthAnchor constraintLessThanOrEqualToConstant:170]]];
    [card addArrangedSubview:ring];
    NSString *caption = self.appID ? @"This app" : [NSString stringWithFormat:@"%@ apps observed",self.summary[@"app_count"] ?: @0];
    [card addArrangedSubview:Text(caption,UIFontTextStyleHeadline,UIColor.secondaryLabelColor)];
}
- (void)categories:(NSArray *)categories in:(UIStackView *)card {
    NSInteger highest = [categories.firstObject[@"count"] integerValue];
    for (NSDictionary *cat in categories) {
        UIStackView *row = Row(); [row addArrangedSubview:Symbol(cat[@"symbol"],CatColor(cat[@"id"]))];
        UILabel *name = Text(cat[@"title"],UIFontTextStyleSubheadline,UIColor.labelColor); [row addArrangedSubview:name];
        UILabel *count = Text(Count(cat[@"count"]),UIFontTextStyleHeadline,UIColor.labelColor); count.textAlignment = NSTextAlignmentRight; [row addArrangedSubview:count];
        [card addArrangedSubview:row];
        UIProgressView *bar = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault]; bar.progressTintColor = CatColor(cat[@"id"]); bar.trackTintColor = UIColor.tertiarySystemFillColor;
        bar.progress = highest ? [cat[@"count"] floatValue]/highest : 0;
        bar.accessibilityLabel = [NSString stringWithFormat:@"%@: %@ recorded actions",cat[@"title"],cat[@"count"]]; [card addArrangedSubview:bar];
    }
}
- (void)signals {
    NSArray *signals = self.summary[@"signals"];
    for (NSUInteger i=0;i<signals.count;i+=2) {
        UIStackView *row = Row(); row.alignment = UIStackViewAlignmentFill; row.distribution = UIStackViewDistributionFillEqually;
        for (NSUInteger j=i;j<MIN(i+2,signals.count);j++) {
            NSDictionary *signal = signals[j]; UIStackView *tile = VStack(); tile.spacing = 7; tile.backgroundColor = UIColor.secondarySystemGroupedBackgroundColor;
            tile.layer.cornerRadius = 20; tile.layoutMarginsRelativeArrangement = YES; tile.layoutMargins = UIEdgeInsetsMake(16,16,16,16);
            [tile addArrangedSubview:Symbol(signal[@"symbol"],Accent())];
            [tile addArrangedSubview:Text(Count(signal[@"count"]),UIFontTextStyleTitle1,UIColor.labelColor)];
            [tile addArrangedSubview:Text(signal[@"title"],UIFontTextStyleCaption1,UIColor.secondaryLabelColor)];
            tile.isAccessibilityElement = YES; tile.accessibilityLabel = [NSString stringWithFormat:@"%@: %@ recorded calls",signal[@"title"],signal[@"count"]];
            tile.isAccessibilityElement = NO;
            UIButton *hit = [UIButton buttonWithType:UIButtonTypeCustom]; hit.translatesAutoresizingMaskIntoConstraints = NO;
            hit.accessibilityLabel = [NSString stringWithFormat:@"%@: %@ calls. Show matching apps",signal[@"title"],signal[@"count"]];
            [tile addSubview:hit];
            [NSLayoutConstraint activateConstraints:@[[hit.leadingAnchor constraintEqualToAnchor:tile.leadingAnchor],[hit.trailingAnchor constraintEqualToAnchor:tile.trailingAnchor],[hit.topAnchor constraintEqualToAnchor:tile.topAnchor],[hit.bottomAnchor constraintEqualToAnchor:tile.bottomAnchor]]];
            __weak typeof(self) weakSelf = self;
            [hit addAction:[UIAction actionWithHandler:^(__kindof UIAction *action) {
                PMInsightsController *apps = [PMInsightsController new]; apps.hours = weakSelf.hours; apps.appID = weakSelf.appID; apps.signalID = signal[@"id"]; apps.appName = signal[@"title"];
                [weakSelf.navigationController pushViewController:apps animated:YES];
            }] forControlEvents:UIControlEventTouchUpInside];
            [row addArrangedSubview:tile];
        } [self.stack addArrangedSubview:row];
    }
}
- (void)history:(UIStackView *)card {
    NSArray *history = self.summary[@"history"]; double highest = 1; for (NSDictionary *b in history) highest = MAX(highest,[b[@"count"] doubleValue]);
    NSDateFormatter *date = [NSDateFormatter new]; date.dateFormat = self.hours == 168 ? @"EEE d" : @"HH:mm";
    for (NSDictionary *bucket in history) {
        UIStackView *row = Row(); UILabel *label = Text([date stringFromDate:[NSDate dateWithTimeIntervalSince1970:[bucket[@"start"] doubleValue]]],UIFontTextStyleCaption1,UIColor.secondaryLabelColor);
        [label.widthAnchor constraintEqualToConstant:62].active = YES; [row addArrangedSubview:label];
        UIProgressView *bar = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault]; bar.progress = [bucket[@"count"] doubleValue]/highest;
        bar.progressTintColor = Accent(); bar.trackTintColor = UIColor.tertiarySystemFillColor;
        bar.accessibilityLabel = label.text; bar.accessibilityValue = [NSString stringWithFormat:@"%@ recorded actions",bucket[@"count"]]; [row addArrangedSubview:bar];
        UILabel *count = Text(Count(bucket[@"count"]),UIFontTextStyleCaption1,UIColor.labelColor); count.textAlignment = NSTextAlignmentRight;
        [count.widthAnchor constraintEqualToConstant:40].active = YES; [row addArrangedSubview:count]; [card addArrangedSubview:row];
    }
}
- (void)apps {
    NSArray *apps = self.summary[@"apps"] ?: @[];
    if (self.signalID) {
        apps = [apps filteredArrayUsingPredicate:[NSPredicate predicateWithBlock:^BOOL(NSDictionary *app, NSDictionary *bindings) { return [app[@"signals"][self.signalID] integerValue] > 0; }]];
        if (!apps.count) [self.stack addArrangedSubview:Text(@"No matching calls in this range",UIFontTextStyleTitle2,UIColor.secondaryLabelColor)];
    }
    for (NSDictionary *app in apps) {
        UIStackView *card = [self card]; UIStackView *row = Row(); [row addArrangedSubview:Symbol(@"app.fill",Accent())];
        [row addArrangedSubview:Text(app[@"name"],UIFontTextStyleHeadline,UIColor.labelColor)];
        UILabel *count = Text(Count(self.signalID ? app[@"signals"][self.signalID] : app[@"count"]),UIFontTextStyleTitle2,UIColor.labelColor); count.textAlignment = NSTextAlignmentRight; [row addArrangedSubview:count]; [card addArrangedSubview:row];
        [card addArrangedSubview:Text(Age(app[@"latest_event"]),UIFontTextStyleCaption1,UIColor.secondaryLabelColor)];
        [self categories:app[@"categories"] in:card];
        __weak typeof(self) weakSelf = self;
        [self button:@"Explore  ›" in:card action:^{ PMCardsController *detail = [PMCardsController new]; detail.appID = app[@"app_id"]; detail.appName = app[@"name"]; detail.hours = weakSelf.hours; [weakSelf.navigationController pushViewController:detail animated:YES]; }];
    }
}
- (void)render {
    for (UIView *v in self.stack.arrangedSubviews) { [self.stack removeArrangedSubview:v]; [v removeFromSuperview]; }
    if (![self isKindOfClass:PMHistoryController.class]) {
        self.period = [[UISegmentedControl alloc] initWithItems:@[@"1 hour",@"24 hours",@"7 days"]]; self.period.selectedSegmentIndex = self.hours == 1 ? 0 : self.hours == 24 ? 1 : 2;
        [self.period addTarget:self action:@selector(rangeChanged:) forControlEvents:UIControlEventValueChanged]; [self.stack addArrangedSubview:self.period];
    }
    UIStackView *status = Row(); [status addArrangedSubview:Symbol(self.failure ? @"wifi.slash" : @"clock.arrow.circlepath",self.failure ? UIColor.secondaryLabelColor : Accent())];
    NSString *stamp = self.failure ?: self.summary ? [NSString stringWithFormat:@"Updated %@",Age(self.summary[@"generated_at"])] : @"Connecting…";
    [status addArrangedSubview:Text(stamp,UIFontTextStyleCaption1,UIColor.secondaryLabelColor)]; [self.stack addArrangedSubview:status];
    if (self.failure && self.summary) [self.stack addArrangedSubview:Text(@"Showing the last refresh",UIFontTextStyleCaption1,UIColor.secondaryLabelColor)];
    if (!self.summary) return;
    if (![self.summary[@"total"] integerValue]) {
        UIStackView *card = [self card]; [card addArrangedSubview:Symbol(@"moon.zzz.fill",Accent())];
        [card addArrangedSubview:Text(@"No recorded actions",UIFontTextStyleTitle2,UIColor.labelColor)];
        [card addArrangedSubview:Text([NSString stringWithFormat:@"Last event: %@",Age(self.summary[@"latest_event"])],UIFontTextStyleSubheadline,UIColor.secondaryLabelColor)];
        [card addArrangedSubview:Text(@"Try another time range or open an app with monitoring enabled.",UIFontTextStyleFootnote,UIColor.secondaryLabelColor)];
    }
    if ([self isKindOfClass:PMInsightsController.class]) { [self apps]; return; }
    if ([self isKindOfClass:PMHistoryController.class]) {
        UIStackView *card = [self card]; [card addArrangedSubview:Text(@"Last seven days",UIFontTextStyleTitle2,UIColor.labelColor)]; [self history:card];
        [card addArrangedSubview:Text(@"Each bar covers 24 hours from the displayed start. Counts, not warnings.",UIFontTextStyleCaption1,UIColor.secondaryLabelColor)];
        UIStackView *mix = [self card]; [self categories:self.summary[@"categories"] in:mix]; return;
    }
    UIStackView *hero = [self card]; [self ring:hero];
    [hero addArrangedSubview:Text([NSString stringWithFormat:@"Last event · %@",Age(self.summary[@"latest_event"])],UIFontTextStyleCaption1,UIColor.secondaryLabelColor)];
    [self signals];
    UIStackView *mix = [self card]; [mix addArrangedSubview:Text(@"Activity mix",UIFontTextStyleTitle2,UIColor.labelColor)]; [self categories:self.summary[@"categories"] in:mix];
    [self.stack addArrangedSubview:Text(@"Recorded calls only · no safety score",UIFontTextStyleCaption1,UIColor.secondaryLabelColor)];
}
@end
@implementation PMHomeController
@end
@implementation PMInsightsController
@end
@implementation PMHistoryController
@end

@implementation PMSettingsController
- (void)viewDidLoad { [super viewDidLoad]; self.title = @"Settings"; self.tableView.rowHeight = UITableViewAutomaticDimension; self.tableView.estimatedRowHeight = 80; }
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 2; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return section == 0 ? 3 : 1; }
- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section { return section == 0 ? @"On this iPhone" : @"Advanced"; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil]; cell.textLabel.numberOfLines = cell.detailTextLabel.numberOfLines = 0;
    cell.textLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody]; cell.textLabel.adjustsFontForContentSizeCategory = YES; cell.selectionStyle = UITableViewCellSelectionStyleNone;
    if (indexPath.section == 0) {
        cell.textLabel.text = @[@"Live local summaries",@"Seven-day history",@"What the counters mean"][indexPath.row];
        cell.detailTextLabel.text = @[@"Refreshes every five seconds while visible. The monitor’s own activity is excluded.",@"Stored locally. No AI connection or account required.",@"Rules count supported API calls. Permission requests, identifiers, and event volume do not establish misuse. Missing events do not prove a feature was unused."][indexPath.row];
    } else {
        cell.textLabel.text = @"Developer Mode"; cell.detailTextLabel.text = @"Raw feed and technical diagnostics";
        UISwitch *toggle = [UISwitch new]; toggle.on = [NSUserDefaults.standardUserDefaults boolForKey:@"PMDeveloperMode"]; toggle.onTintColor = Accent();
        [toggle addTarget:self action:@selector(toggle:) forControlEvents:UIControlEventValueChanged]; cell.accessoryView = toggle;
    } return cell;
}
- (void)toggle:(UISwitch *)toggle { [NSUserDefaults.standardUserDefaults setBool:toggle.on forKey:@"PMDeveloperMode"]; [NSNotificationCenter.defaultCenter postNotificationName:@"PMDeveloperModeChanged" object:nil]; }
@end
@implementation PMDeveloperController
- (void)viewDidLoad { [super viewDidLoad]; self.title = @"Developer"; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return 3; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil]; cell.textLabel.text = @[@"App diagnostics",@"Raw activity feed",@"Local dashboard"][indexPath.row]; cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator; return cell;
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    if (indexPath.row < 2) [self.navigationController pushViewController:PMActivityScreen(indexPath.row == 0) animated:YES];
    else [UIApplication.sharedApplication openURL:[NSURL URLWithString:@"http://127.0.0.1:8800/"] options:@{} completionHandler:nil];
}
@end
