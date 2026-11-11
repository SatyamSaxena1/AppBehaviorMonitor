#import <UIKit/UIKit.h>
UIViewController *PMActivityScreen(BOOL apps);
@interface PMCardsController : UIViewController
@end
@interface PMHomeController : PMCardsController
@end
@interface PMInsightsController : PMCardsController
@end
@interface PMSettingsController : UITableViewController
@end
@interface PMDeveloperController : UITableViewController
@end

@interface PMHistoryController : PMCardsController
@end
