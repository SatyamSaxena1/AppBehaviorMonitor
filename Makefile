THEOS = /var/theos
TARGET = iphone:clang:15.6:15.0
ARCHS = arm64
THEOS_PACKAGE_SCHEME = rootless

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = AppBehaviorMonitor
AppBehaviorMonitor_FILES = Tweak.x
AppBehaviorMonitor_CFLAGS = -fobjc-arc -Wall -Wno-unused-variable
AppBehaviorMonitor_FRAMEWORKS = Foundation UIKit CoreLocation AVFoundation Security
AppBehaviorMonitor_PRIVATE_FRAMEWORKS = AppTrackingTransparency

include $(THEOS_MAKE_PATH)/tweak.mk

after-install::
	install.exec "sbreload"
