#import "InsightsUI.h"
#import "MCPSetupController.h"

static BOOL Developer(void) { return [NSUserDefaults.standardUserDefaults boolForKey:@"PMDeveloperMode"]; }
static UIColor *Amber(void) { return [UIColor colorWithRed:.96 green:.59 blue:.24 alpha:1]; }
static NSString *ReviewRequest(void) { return @"Review my last 24 hours of supported app activity in Privacy Monitor. Save a few useful, evidence-backed insights into the app. Separate observed facts from possible explanations, explain limitations and confidence, and suggest practical next steps. Do not declare an app malicious from event counts or domain names alone."; }
static NSString *DateText(id number) {
    if (![number respondsToSelector:@selector(doubleValue)]) return @"Not recorded";
    NSDateFormatter *format = [NSDateFormatter new]; format.dateStyle = NSDateFormatterMediumStyle; format.timeStyle = NSDateFormatterShortStyle;
    return [format stringFromDate:[NSDate dateWithTimeIntervalSince1970:[number doubleValue]]];
}
static UILabel *Label(NSString *text, UIFontTextStyle style, UIColor *color) {
    UILabel *label = [UILabel new]; label.text = text ?: @""; label.font = [UIFont preferredFontForTextStyle:style];
    label.adjustsFontForContentSizeCategory = YES; label.numberOfLines = 0; label.textColor = color; return label;
}
static UIStackView *Stack(void) {
    UIStackView *stack = [UIStackView new]; stack.axis = UILayoutConstraintAxisVertical; stack.spacing = 12; return stack;
}
static void RequestReview(UIViewController *vc, UIView *source) {
    UIActivityViewController *share = [[UIActivityViewController alloc] initWithActivityItems:@[ReviewRequest()] applicationActivities:nil];
    share.popoverPresentationController.sourceView = source ?: vc.view;
    share.popoverPresentationController.sourceRect = source ? source.bounds : CGRectMake(vc.view.bounds.size.width/2, 80, 1, 1);
    [vc presentViewController:share animated:YES completion:nil];
}

@interface PMCardsController ()
@property UIScrollView *scroll;
@property UIStackView *stack;
@property UIRefreshControl *refresh;
@property NSArray *insights;
@property NSDictionary *health;
@property NSInteger pending;
@property NSString *failure;
- (void)render;
- (void)load;
- (UIStackView *)card;
- (void)button:(NSString *)title in:(UIStackView *)stack action:(void (^)(void))action;
- (void)showInsight:(NSDictionary *)insight;
@end
@interface PMInsightDetailController : PMCardsController
@property NSDictionary *insight;
@end

@implementation PMCardsController
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor = UIColor.systemGroupedBackgroundColor;
    self.scroll = [UIScrollView new]; self.scroll.alwaysBounceVertical = YES; self.scroll.translatesAutoresizingMaskIntoConstraints = NO;
    self.stack = Stack(); self.stack.spacing = 18; self.stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.view addSubview:self.scroll]; [self.scroll addSubview:self.stack];
    [NSLayoutConstraint activateConstraints:@[
      [self.scroll.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor],
      [self.scroll.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor],
      [self.scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],
      [self.scroll.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
      [self.stack.leadingAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.leadingAnchor constant:20],
      [self.stack.trailingAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.trailingAnchor constant:-20],
      [self.stack.topAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.topAnchor constant:12],
      [self.stack.bottomAnchor constraintEqualToAnchor:self.scroll.contentLayoutGuide.bottomAnchor constant:-30],
      [self.stack.widthAnchor constraintEqualToAnchor:self.scroll.frameLayoutGuide.widthAnchor constant:-40]]];
    self.insights = @[];
    if (![self isKindOfClass:PMInsightDetailController.class]) {
        self.refresh = [UIRefreshControl new]; [self.refresh addTarget:self action:@selector(load) forControlEvents:UIControlEventValueChanged];
        self.scroll.refreshControl = self.refresh;
    }
    [self render];
}
- (void)viewDidAppear:(BOOL)animated { [super viewDidAppear:animated]; if (![self isKindOfClass:PMInsightDetailController.class]) [self load]; }
- (UIStackView *)card {
    UIStackView *card = Stack(); card.backgroundColor = UIColor.secondarySystemGroupedBackgroundColor;
    card.layer.cornerRadius = 24; card.layoutMargins = UIEdgeInsetsMake(22,22,22,22); card.layoutMarginsRelativeArrangement = YES;
    [self.stack addArrangedSubview:card]; return card;
}
- (void)clear { for (UIView *view in self.stack.arrangedSubviews) { [self.stack removeArrangedSubview:view]; [view removeFromSuperview]; } }
- (void)button:(NSString *)title in:(UIStackView *)stack action:(void (^)(void))action {
    UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration *config = [UIButtonConfiguration filledButtonConfiguration]; config.title = title;
    config.baseBackgroundColor = Amber(); config.baseForegroundColor = UIColor.blackColor;
    config.cornerStyle = UIButtonConfigurationCornerStyleLarge; config.contentInsets = NSDirectionalEdgeInsetsMake(14,16,14,16);
    button.configuration = config;
    [button addAction:[UIAction actionWithHandler:^(__kindof UIAction *sender) { action(); }] forControlEvents:UIControlEventTouchUpInside];
    [stack addArrangedSubview:button];
}
- (void)load {
    if (self.pending) return;
    self.pending = 2; self.failure = nil;
    __weak typeof(self) weakSelf = self;
    for (NSString *route in @[@"insights", @"health"]) {
        NSURL *url = [NSURL URLWithString:[@"http://127.0.0.1:8800/api/" stringByAppendingString:route]];
        NSURLRequest *request = [NSURLRequest requestWithURL:url cachePolicy:NSURLRequestReloadIgnoringLocalCacheData timeoutInterval:8];
        [[NSURLSession.sharedSession dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
            id json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
            BOOL ok = !error && [(NSHTTPURLResponse *)response statusCode] == 200 && [json isKindOfClass:NSDictionary.class];
            dispatch_async(dispatch_get_main_queue(), ^{
                PMCardsController *self = weakSelf; if (!self) return;
                if (!ok) self.failure = @"Can’t refresh right now. Your last loaded reviews stay here. Check that the jailbreak and Privacy Monitor activity service are running.";
                else if ([route isEqual:@"insights"] && [json[@"insights"] isKindOfClass:NSArray.class]) self.insights = json[@"insights"];
                else if ([route isEqual:@"health"]) self.health = json;
                self.pending--;
                if (!self.pending) { [self.refresh endRefreshing]; [self render]; }
            });
        }] resume];
    }
}
- (void)showInsight:(NSDictionary *)insight {
    PMInsightDetailController *detail = [PMInsightDetailController new]; detail.insight = insight;
    [self.navigationController pushViewController:detail animated:YES];
}
- (void)render { }
- (void)emptyCard {
    UIStackView *card = [self card];
    [card addArrangedSubview:Label(@"No AI reviews yet.", UIFontTextStyleTitle2, UIColor.labelColor)];
    [card addArrangedSubview:Label(@"Ask your connected assistant to review recorded activity. Its saved findings will appear here.", UIFontTextStyleBody, UIColor.secondaryLabelColor)];
    __weak typeof(self) weakSelf = self;
    [self button:@"Ask for a review" in:card action:^{ if (weakSelf) RequestReview(weakSelf, nil); }];
    [card addArrangedSubview:Label(@"Sharing prepares a request. You choose which assistant receives it. Connection setup is available in Developer Mode.", UIFontTextStyleFootnote, UIColor.secondaryLabelColor)];
}
- (void)insightCard:(NSDictionary *)insight {
    UIStackView *card = [self card];
    NSString *badge = [insight[@"priority"] isEqual:@"review"] ? @"AI INSIGHT · WORTH A LOOK" : @"AI INSIGHT · FOR CONTEXT";
    [card addArrangedSubview:Label(badge, UIFontTextStyleCaption1, UIColor.systemOrangeColor)];
    [card addArrangedSubview:Label(insight[@"title"], UIFontTextStyleTitle2, UIColor.labelColor)];
    [card addArrangedSubview:Label(insight[@"summary"], UIFontTextStyleBody, UIColor.secondaryLabelColor)];
    [card addArrangedSubview:Label([NSString stringWithFormat:@"%@ · %@", insight[@"author"] ?: @"AI assistant", DateText(insight[@"created_at"])], UIFontTextStyleFootnote, UIColor.secondaryLabelColor)];
    __weak typeof(self) weakSelf = self;
    [self button:@"Read the finding" in:card action:^{ [weakSelf showInsight:insight]; }];
}
@end

@implementation PMHomeController
- (void)viewDidLoad { self.title = @"Overview"; [super viewDidLoad]; }
- (void)render {
    [self clear];
    UIStackView *hero = [self card];
    UIImageView *art = [[UIImageView alloc] initWithImage:[UIImage imageNamed:@"PrivacyArtwork"]]; art.contentMode = UIViewContentModeScaleAspectFit; art.layer.cornerRadius = 18; art.clipsToBounds = YES;
    art.isAccessibilityElement = NO; [art.heightAnchor constraintEqualToConstant:110].active = YES; [hero addArrangedSubview:art];
    [hero addArrangedSubview:Label(@"Your apps, explained.", UIFontTextStyleTitle1, UIColor.labelColor)];
    [hero addArrangedSubview:Label(@"AI reviews with recorded facts, context, and practical next steps.", UIFontTextStyleBody, UIColor.secondaryLabelColor)];
    UIStackView *status = [self card];
    [status addArrangedSubview:Label(self.failure ? @"Showing your last refresh" : self.health ? @"Activity is available" : @"Checking your activity…", UIFontTextStyleHeadline, UIColor.labelColor)];
    [status addArrangedSubview:Label(self.health ? [NSString stringWithFormat:@"%lu saved AI reviews · Latest recorded activity: %@", (unsigned long)self.insights.count, DateText(self.health[@"latest_event"])] : @"Pull down to refresh. An empty history can mean no supported actions were observed.", UIFontTextStyleSubheadline, UIColor.secondaryLabelColor)];
    if (self.failure) { UIStackView *error = [self card]; [error addArrangedSubview:Label(self.failure, UIFontTextStyleBody, UIColor.secondaryLabelColor)]; }
    if (self.insights.count) [self insightCard:self.insights.firstObject]; else [self emptyCard];
    UIStackView *note = [self card]; [note addArrangedSubview:Label(@"A review, not a verdict.", UIFontTextStyleHeadline, UIColor.labelColor)];
    [note addArrangedSubview:Label(@"Only supported actions in monitored apps are visible. Missing events don’t prove that an app never used a feature.", UIFontTextStyleBody, UIColor.secondaryLabelColor)];
}
@end

@implementation PMInsightsController
- (void)viewDidLoad { self.title = @"AI Insights"; [super viewDidLoad]; }
- (void)render {
    [self clear];
    [self.stack addArrangedSubview:Label(@"Findings you can understand—and check.", UIFontTextStyleTitle2, UIColor.labelColor)];
    if (self.failure) [self.stack addArrangedSubview:Label(self.failure, UIFontTextStyleBody, UIColor.secondaryLabelColor)];
    if (!self.insights.count) [self emptyCard];
    for (NSDictionary *insight in self.insights) [self insightCard:insight];
}
@end

@implementation PMInsightDetailController
- (void)viewDidLoad { self.title = @"The finding"; [super viewDidLoad]; }
- (void)render {
    [self clear]; NSDictionary *item = self.insight;
    UIStackView *head = [self card];
    [head addArrangedSubview:Label(@"AI-GENERATED ANALYSIS", UIFontTextStyleCaption1, UIColor.systemOrangeColor)];
    [head addArrangedSubview:Label(item[@"title"], UIFontTextStyleTitle1, UIColor.labelColor)];
    [head addArrangedSubview:Label(item[@"summary"], UIFontTextStyleBody, UIColor.secondaryLabelColor)];
    NSArray *keys = @[@"observations", @"interpretation", @"recommendations"];
    NSArray *titles = @[@"What was observed", @"What it could mean", @"What you can do"];
    for (NSInteger i=0; i<3; i++) {
        UIStackView *card = [self card]; [card addArrangedSubview:Label(titles[i], UIFontTextStyleHeadline, UIColor.labelColor)];
        id value = item[keys[i]];
        if ([value isKindOfClass:NSArray.class]) for (NSString *line in value) [card addArrangedSubview:Label([@"• " stringByAppendingString:line], UIFontTextStyleBody, UIColor.secondaryLabelColor)];
        else [card addArrangedSubview:Label(value, UIFontTextStyleBody, UIColor.secondaryLabelColor)];
    }
    UIStackView *limits = [self card];
    [limits addArrangedSubview:Label(@"How much to rely on this", UIFontTextStyleHeadline, UIColor.labelColor)];
    [limits addArrangedSubview:Label([NSString stringWithFormat:@"Evidence confidence: %@", [item[@"confidence"] capitalizedString]], UIFontTextStyleSubheadline, UIColor.labelColor)];
    [limits addArrangedSubview:Label(item[@"limitations"], UIFontTextStyleBody, UIColor.secondaryLabelColor)];
    [limits addArrangedSubview:Label([NSString stringWithFormat:@"Review window: %@ – %@\nSaved %@ · Author label: %@",DateText(item[@"period_start"]),DateText(item[@"period_end"]),DateText(item[@"created_at"]),item[@"author"] ?: @"AI assistant"], UIFontTextStyleFootnote, UIColor.secondaryLabelColor)];
    UIStackView *evidence = [self card];
    [evidence addArrangedSubview:Label(@"The recorded evidence", UIFontTextStyleHeadline, UIColor.labelColor)];
    NSDictionary *actions = @{@"identifierForVendor":@"Read an app-vendor identifier", @"data_task":@"Created a network request", @"copy_matching":@"Requested saved credentials", @"get_string":@"Read the clipboard"};
    for (NSDictionary *event in item[@"evidence"]) {
        NSString *name = [event[@"display_name"] isKindOfClass:NSString.class] && [event[@"display_name"] length] ? event[@"display_name"] : event[@"exe_name"];
        NSString *action = actions[event[@"action"]] ?: @"A supported action was recorded";
        [evidence addArrangedSubview:Label([NSString stringWithFormat:@"%@ · %@\n%@%@",name ?: @"App",DateText(event[@"timestamp"]),action,event[@"domain"] ? [@" · " stringByAppendingString:event[@"domain"]] : @""], UIFontTextStyleBody, UIColor.secondaryLabelColor)];
        if (Developer()) [evidence addArrangedSubview:Label([NSString stringWithFormat:@"Event %@ · %@ · %@/%@",event[@"id"],event[@"app_id"],event[@"category"],event[@"action"]], UIFontTextStyleCaption1, UIColor.secondaryLabelColor)];
    }
}
@end

@implementation PMSettingsController
- (void)viewDidLoad { [super viewDidLoad]; self.title = @"Settings"; }
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 3; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return section == 0 ? 2 : 1; }
- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section { return @[@"Your AI reviews", @"On this iPhone", @"For developers"][section]; }
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    if (section == 2) return @"Shows raw activity, app identifiers, technical evidence, and MCP connection setup. Off by default.";
    return nil;
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.textLabel.numberOfLines = cell.detailTextLabel.numberOfLines = 0;
    cell.textLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody]; cell.textLabel.adjustsFontForContentSizeCategory = YES;
    if (indexPath.section == 0) {
        cell.textLabel.text = indexPath.row == 0 ? @"Ask an assistant for a review" : @"How AI reviews work";
        cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
    } else if (indexPath.section == 1) {
        cell.textLabel.text = @"Your history stays on this device";
        cell.detailTextLabel.text = @"Recorded activity is retained for seven days. Saved AI reviews are retained for seven days after creation. Results sent to a connected AI enter that conversation.";
        cell.selectionStyle = UITableViewCellSelectionStyleNone;
    } else {
        cell.textLabel.text = @"Developer Mode";
        UISwitch *toggle = [UISwitch new]; toggle.on = Developer(); toggle.onTintColor = Amber();
        [toggle addTarget:self action:@selector(toggleDeveloper:) forControlEvents:UIControlEventValueChanged]; cell.accessoryView = toggle; cell.selectionStyle = UITableViewCellSelectionStyleNone;
    }
    return cell;
}
- (void)toggleDeveloper:(UISwitch *)toggle {
    [NSUserDefaults.standardUserDefaults setBool:toggle.on forKey:@"PMDeveloperMode"];
    [NSNotificationCenter.defaultCenter postNotificationName:@"PMDeveloperModeChanged" object:nil];
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES]; if (indexPath.section != 0) return;
    if (indexPath.row == 0) { RequestReview(self, [tableView cellForRowAtIndexPath:indexPath]); return; }
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:@"You ask. Your assistant reviews." message:@"A connected assistant reads recorded metadata when you request a review, then can save evidence-backed findings into this app. Facts and explanations are shown separately. No model runs automatically in the background. Enable Developer Mode for connection setup and diagnostic views." preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"Got it" style:UIAlertActionStyleDefault handler:nil]]; [self presentViewController:alert animated:YES completion:nil];
}
@end

@implementation PMDeveloperController
- (void)viewDidLoad { [super viewDidLoad]; self.title = @"Developer"; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return 4; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil];
    cell.textLabel.text = @[@"App diagnostics", @"Raw activity feed", @"MCP connection setup", @"Open local dashboard"][indexPath.row]; cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator; return cell;
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    UIViewController *screen;
    if (indexPath.row < 2) screen = PMActivityScreen(indexPath.row == 0);
    else if (indexPath.row == 2) screen = [[MCPSetupController alloc] initWithStyle:UITableViewStyleInsetGrouped];
    else { [UIApplication.sharedApplication openURL:[NSURL URLWithString:@"http://127.0.0.1:8800/"] options:@{} completionHandler:nil]; return; }
    [self.navigationController pushViewController:screen animated:YES];
}
@end
