# Device label helper

`assets/device_labels.dex` is a tiny `app_process` program that asks Android's
`PackageManager` for the visible label of every installed app. The Packages tab
writes it to `/data/local/tmp`, runs it as the shell user, then removes it in
one `adb exec-out` round-trip.

This is needed because newer Android releases no longer include
`nonLocalizedLabel` in `dumpsys package packages`. No root access is required.

## Rebuilding the dex

With an Android SDK installed:

```bash
javac --release 8 \
    -cp "$ANDROID_HOME/platforms/android-35/android.jar" \
    -d classes DeviceLabels.java
d8 --lib "$ANDROID_HOME/platforms/android-35/android.jar" \
    --output . classes/DeviceLabels.class
cp classes.dex ../../assets/device_labels.dex
```

The checked-in dex was built with Android SDK 35 and tested on Android 15.
The Python side falls back to the old `dumpsys` parser if this helper cannot
run on a particular device.
