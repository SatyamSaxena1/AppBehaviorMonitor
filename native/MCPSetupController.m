#import "MCPSetupController.h"

static NSString *const Launcher = @"/var/jb/usr/libexec/privacy-monitor/launch-mcp";
@interface MCPSetupController () <UITextFieldDelegate>
@property UITextField *hostInput;
@end

@implementation MCPSetupController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"Connect AI";
    self.tableView.rowHeight = UITableViewAutomaticDimension;
    self.tableView.estimatedRowHeight = 78;
    self.hostInput = [UITextField new];
    self.hostInput.placeholder = @"iPhone IP or hostname";
    self.hostInput.accessibilityLabel = @"iPhone SSH host";
    self.hostInput.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    self.hostInput.adjustsFontForContentSizeCategory = YES;
    self.hostInput.autocapitalizationType = UITextAutocapitalizationTypeNone;
    self.hostInput.autocorrectionType = UITextAutocorrectionTypeNo;
    self.hostInput.keyboardType = UIKeyboardTypeURL;
    self.hostInput.returnKeyType = UIReturnKeyDone;
    self.hostInput.delegate = self;
}
- (BOOL)textFieldShouldReturn:(UITextField *)field { [field resignFirstResponder]; return YES; }
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 6; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return section == 1 || section == 2 ? 3 : section == 4 ? 3 : 1;
}
- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    return @[@"Read-only AI connection", @"AI client on this iPhone", @"AI client on your computer", @"What you share", @"Available tools", @"More help"][section];
}
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    if (section == 1) return @"Run the copied command in your on-device Claude Code or Codex CLI. The JSON option is for stdio clients running on this iPhone. Start a new AI session afterward.";
    if (section == 2) return @"Enter the iPhone’s reachable IP or hostname. Set up key-based SSH for the mobile user first. SSH config works with compatible desktop clients; it is not a hosted MCP URL.";
    return nil;
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.textLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    cell.detailTextLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleFootnote];
    cell.textLabel.adjustsFontForContentSizeCategory = YES;
    cell.detailTextLabel.adjustsFontForContentSizeCategory = YES;
    cell.textLabel.numberOfLines = cell.detailTextLabel.numberOfLines = 0;
    cell.detailTextLabel.textColor = UIColor.secondaryLabelColor;
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    NSInteger section = indexPath.section, row = indexPath.row;
    if (section == 0) {
        BOOL installed = [NSFileManager.defaultManager fileExistsAtPath:Launcher];
        cell.textLabel.text = installed ? @"Connector installed" : @"Collector update needed";
        cell.detailTextLabel.text = installed ? @"Connect a compatible client to ask about recorded activity. Nothing is uploaded automatically." : @"Update Privacy Monitor and its collector in Sileo to install the MCP launcher.";
        cell.imageView.image = [UIImage systemImageNamed:installed ? @"checkmark.shield.fill" : @"arrow.down.circle"];
        cell.imageView.tintColor = UIColor.systemOrangeColor;
    } else if (section == 1) {
        cell.textLabel.text = @[@"Copy Claude Code command", @"Copy Codex command", @"Copy on-device MCP JSON"][row];
        cell.imageView.image = [UIImage systemImageNamed:@"doc.on.doc"];
        cell.selectionStyle = UITableViewCellSelectionStyleDefault;
    } else if (section == 2) {
        if (row == 0) {
            self.hostInput.frame = CGRectInset(cell.contentView.bounds, 16, 10);
            self.hostInput.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
            [cell.contentView addSubview:self.hostInput];
        } else {
            cell.textLabel.text = row == 1 ? @"Copy SSH MCP JSON" : @"Share SSH MCP configuration…";
            cell.imageView.image = [UIImage systemImageNamed:row == 1 ? @"doc.on.doc" : @"square.and.arrow.up"];
            cell.selectionStyle = UITableViewCellSelectionStyleDefault;
        }
    } else if (section == 3) {
        cell.textLabel.text = @"Tool results enter your AI conversation. The connector omits clipboard contents, raw file paths, full URLs, and credential details. It exposes no shell commands or settings changes. Counts and domain names are observations, not a verdict that an app is malicious.";
    } else if (section == 4) {
        cell.textLabel.text = @[@"activity_summary", @"recent_activity", @"contacted_domains"][row];
        cell.detailTextLabel.text = @[@"Counts by app and category, over a bounded time window.", @"Recent event metadata without raw details.", @"Domain observations from a bounded network-event sample."][row];
    } else {
        cell.textLabel.text = @"Open setup guide";
        cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
        cell.selectionStyle = UITableViewCellSelectionStyleDefault;
    }
    return cell;
}
- (void)message:(NSString *)title text:(NSString *)text {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:title message:text preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}
- (NSString *)configuration:(BOOL)ssh {
    NSArray *args = @[@"/var/jb/bin/sh", Launcher];
    NSString *command = args[0];
    args = @[Launcher];
    if (ssh) {
        NSString *host = [self.hostInput.text stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:"];
        if (!host.length || host.length > 253 || [host hasPrefix:@"-"] || [host rangeOfCharacterFromSet:allowed.invertedSet].location != NSNotFound) {
            [self message:@"Enter your iPhone’s address" text:@"Use its reachable IP address or hostname, without a username, port, spaces, or URL scheme. SSH must already work with your key."];
            return nil;
        }
        command = @"ssh";
        args = @[@"-T", @"-o", @"BatchMode=yes", [@"mobile@" stringByAppendingString:host], @"/var/jb/bin/sh", Launcher];
    }
    NSDictionary *config = @{@"mcpServers": @{@"privacy-monitor": @{@"command": command, @"args": args}}};
    NSData *data = [NSJSONSerialization dataWithJSONObject:config options:NSJSONWritingPrettyPrinted error:nil];
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    [self.hostInput resignFirstResponder];
    if (indexPath.section == 5) {
        [UIApplication.sharedApplication openURL:[NSURL URLWithString:@"https://satyamsaxena1.github.io/privacy-monitor/#connect"] options:@{} completionHandler:nil];
        return;
    }
    NSString *text;
    if (indexPath.section == 1) {
        text = indexPath.row == 0 ? [@"claude mcp add --scope user --transport stdio privacy-monitor -- /var/jb/bin/sh " stringByAppendingString:Launcher] : indexPath.row == 1 ? [@"codex mcp add privacy-monitor -- /var/jb/bin/sh " stringByAppendingString:Launcher] : [self configuration:NO];
    } else if (indexPath.section == 2 && indexPath.row > 0) {
        text = [self configuration:YES];
    } else return;
    if (!text) return;
    if (indexPath.section == 2 && indexPath.row == 2) {
        UIActivityViewController *share = [[UIActivityViewController alloc] initWithActivityItems:@[text] applicationActivities:nil];
        share.popoverPresentationController.sourceView = [tableView cellForRowAtIndexPath:indexPath];
        share.popoverPresentationController.sourceRect = [tableView cellForRowAtIndexPath:indexPath].bounds;
        [self presentViewController:share animated:YES completion:nil];
    } else {
        UIPasteboard.generalPasteboard.string = text;
        [self message:@"Copied" text:@"Paste into the matching AI client’s terminal or MCP configuration. Copying does not connect the client or send activity."];
    }
}
@end
