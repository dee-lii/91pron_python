# Redmi G Pro 27U ADB tools

Small zero-dependency helper for inspecting and controlling a Redmi G Pro 27U
monitor at `192.168.31.52`.

The useful screen path is Android/HyperOS ADB:

- `adb exec-out screencap -p` returns the current Android framebuffer as PNG.
- `uiautomator dump` returns text and bounds for visible Android UI nodes.
- `input keyevent` can send volume, navigation, and media keys.

I did not find a public vendor HTTP API for screenshots. If the monitor exposes
one, first run `probe-ports` and inspect the open services.

## Prerequisites

Install Android platform-tools:

```sh
brew install android-platform-tools
```

Then authorize ADB on the monitor if it asks.

## Commands

```sh
cd /Users/deelii/code/redmi-gpro27u-tools

# Check ADB, connect to the monitor, and print basic properties.
./redmi_gpro27u.py doctor

# Capture one screenshot.
./redmi_gpro27u.py screenshot

# Serve a local web page that refreshes the screenshot once per second.
./redmi_gpro27u.py view

# Dump visible Android UI text/bounds.
./redmi_gpro27u.py ui -o captures/window.xml

# Volume controls.
./redmi_gpro27u.py volume up
./redmi_gpro27u.py volume down
./redmi_gpro27u.py volume mute
./redmi_gpro27u.py volume set 8

# Navigation / raw key events.
./redmi_gpro27u.py key home
./redmi_gpro27u.py key back
./redmi_gpro27u.py key ok
./redmi_gpro27u.py key 24

# Probe common TCP ports on the monitor.
./redmi_gpro27u.py probe-ports
./redmi_gpro27u.py probe-ports --ports 1-10000
```

The default target is `192.168.31.52:5555`. Override it with:

```sh
REDMI_GPRO27U_HOST=192.168.31.52 REDMI_GPRO27U_PORT=5555 ./redmi_gpro27u.py doctor
```

## Notes

ADB screenshot usually captures the smart Android/HyperOS surface. External
HDMI/DP input may appear black or protected depending on how the monitor routes
the video plane.
