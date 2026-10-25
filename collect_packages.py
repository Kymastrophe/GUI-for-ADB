#!/usr/bin/env python3
"""
collect_packages.py

Build or update data/packages.json from all open-source debloat lists.
Existing names are merged in, so locally harvested entries are never lost.
Requires internet access. Takes ~30 seconds.

Usage:
    python collect_packages.py [--output path/to/packages.json]
"""

import json
import re
import argparse
import urllib.request
from pathlib import Path

# ── Name cleaning ─────────────────────────────────────────────────────────────

def clean_name(raw: str) -> str | None:
    """
    Extract a clean human-readable app name from the first line of a
    UAD-style description string.
    """
    if not raw:
        return None
    name = raw.split("\n")[0].strip().rstrip(".")

    # Cut at ' - description' or ': description'
    for sep in [" - ", ": "]:
        if sep in name:
            name = name.split(sep)[0].strip()

    # Cut at '. Sentence starts' (e.g. 'Block Blast. A casual game...')
    dot_match = re.search(r"\. [A-Z]", name)
    if dot_match:
        name = name[: dot_match.start()].strip()

    # Cut at common trailing clauses
    for discard in [
        ", safe to remove", ", based on", ", default",
        ", stock", ", pre-installed", ", replaced by",
    ]:
        idx = name.lower().find(discard.lower())
        if idx != -1:
            name = name[:idx].strip()

    # Hard cap
    if len(name) > 55 or "http" in name.lower():
        return None

    # Filter descriptions masquerading as names
    bad_starts = (
        "refers ", "this app", "the package", "a set of",
        "it can", "used to", "part of ", "may break", "looks to be",
        "not safe", "probably ", "removing ", "could be ", "enables ",
        "provides ", "allows ", "handles ", "manages ", "controls ",
        "required for", "needed for", "android system",
        "reminder", "note:", "warning",
    )
    if any(name.lower().startswith(b) for b in bad_starts):
        return None

    return name if len(name) > 1 else None


# ── HTTP fetch ────────────────────────────────────────────────────────────────

def fetch(url: str, timeout: int = 25) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "adb-manager/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        print(f"  ⚠  Could not fetch {url}: {e}")
        return None


# ── Sources ───────────────────────────────────────────────────────────────────

def load_uad_ng(result: dict) -> int:
    """
    Universal Android Debloater Next Generation — the most comprehensive source.
    Format: { "pkg.name": { "list": "Oem|Google|Aosp|Carrier|Misc", "description": "Name\ndetails..." } }
    ~5400 packages covering Samsung, Huawei, Xiaomi, Motorola, LG, OnePlus, Vivo,
    OPPO/ColorOS, Sony, Asus, ZTE, Nubia, TCL, Transsion, MediaTek, Qualcomm,
    LineageOS, carriers (Verizon, AT&T, T-Mobile, Sprint, etc.)
    """
    print("Fetching UAD-NG (Universal Android Debloater Next Generation)...")
    raw = fetch(
        "https://raw.githubusercontent.com/Universal-Debloater-Alliance/"
        "universal-android-debloater-next-generation/main/resources/assets/uad_lists.json"
    )
    if not raw:
        return 0
    d = json.loads(raw)
    count = 0
    for pkg, info in d.items():
        name = clean_name(info.get("description", ""))
        if pkg not in result or not result[pkg]:
            result[pkg] = name or ""
        count += 1
    print(f"  ✓  {count:,} packages")
    return count


def load_muntashir_akon(result: dict) -> int:
    """
    MuntashirAkon android-debloat-list — has 'label' fields (real names) for many entries.
    Separate files: aosp, google, carrier, oem (3758 OEM entries alone).
    """
    base = "https://raw.githubusercontent.com/MuntashirAkon/android-debloat-list/master"
    total = 0
    for fname in ["aosp", "google", "carrier", "oem"]:
        print(f"Fetching MuntashirAkon/{fname}.json...")
        raw = fetch(f"{base}/{fname}.json")
        if not raw:
            continue
        try:
            entries = json.loads(raw)
        except Exception as e:
            print(f"  ⚠  parse error: {e}")
            continue
        count = 0
        for entry in entries:
            pkg = entry.get("id", "")
            if not pkg:
                continue
            # Prefer explicit 'label' field, fall back to description parsing
            label = entry.get("label") or clean_name(entry.get("description", ""))
            if pkg not in result:
                result[pkg] = label or ""
            elif label and not result[pkg]:
                result[pkg] = label
            count += 1
        total += count
        print(f"  ✓  {count:,} packages")
    return total


# ── Inline vendor packages not covered by the above ──────────────────────────
# Curated manually from AOSP source, OEM firmware dumps, and carrier APK lists.

INLINE_PACKAGES: dict[str, str] = {

    # ── AOSP / Android core ──────────────────────────────────────────────────
    "android": "Android System",
    "android.autoinstalls.config": "Play Auto Installs Config",
    "com.android.backupconfirm": "Backup Confirmation",
    "com.android.bips": "Default Print Service",
    "com.android.bluetooth": "Bluetooth",
    "com.android.bluetoothmidiservice": "Bluetooth MIDI Service",
    "com.android.browser": "AOSP Browser",
    "com.android.calllogbackup": "Call Log Backup",
    "com.android.camera": "AOSP Camera",
    "com.android.camera2": "AOSP Camera2",
    "com.android.captiveportallogin": "Captive Portal Login",
    "com.android.carrierconfig": "Carrier Config",
    "com.android.cellbroadcastreceiver": "Cell Broadcast Receiver",
    "com.android.cellbroadcastservice": "Cell Broadcast Service",
    "com.android.certinstaller": "Certificate Installer",
    "com.android.chrome": "Google Chrome",
    "com.android.companiondevicemanager": "Companion Device Manager",
    "com.android.contacts": "AOSP Contacts",
    "com.android.credentials.selection": "Credential Selector",
    "com.android.defcontainer": "Package Access Helper",
    "com.android.deskclock": "AOSP Clock",
    "com.android.dialer": "AOSP Phone",
    "com.android.dreams.basic": "Basic Screensavers",
    "com.android.dreams.phototable": "Photo Table Screensaver",
    "com.android.egg": "Android Easter Egg",
    "com.android.email": "AOSP Email",
    "com.android.emergency": "Emergency Alerts",
    "com.android.externalstorage": "External Storage",
    "com.android.facelock": "Trusted Face Unlock",
    "com.android.gallery": "AOSP Gallery",
    "com.android.gallery3d": "AOSP Gallery 3D",
    "com.android.htmlviewer": "HTML Viewer",
    "com.android.inputdevices": "Input Devices",
    "com.android.inputmethod.latin": "AOSP Keyboard",
    "com.android.inputmethod.pinyin": "Pinyin IME",
    "com.android.keychain": "Key Chain",
    "com.android.launcher": "AOSP Launcher",
    "com.android.launcher2": "AOSP Launcher2",
    "com.android.launcher3": "AOSP Launcher3",
    "com.android.mms": "AOSP MMS",
    "com.android.mtp": "MTP Application",
    "com.android.music": "AOSP Music",
    "com.android.nfc": "NFC Service",
    "com.android.packageinstaller": "Package Installer",
    "com.android.phone": "Phone Service",
    "com.android.printspooler": "Print Spooler",
    "com.android.providers.blockednumber": "Blocked Number Provider",
    "com.android.providers.calendar": "Calendar Storage",
    "com.android.providers.contacts": "Contacts Storage",
    "com.android.providers.downloads": "Download Manager",
    "com.android.providers.downloads.ui": "Downloads",
    "com.android.providers.media": "Media Storage",
    "com.android.providers.settings": "Settings Storage",
    "com.android.providers.telephony": "Telephony Provider",
    "com.android.providers.userdictionary": "User Dictionary",
    "com.android.quicksearchbox": "Search",
    "com.android.retaildemo": "Retail Demo",
    "com.android.se": "Secure Element Service",
    "com.android.server.telecom": "Telecom Service",
    "com.android.settings": "Settings",
    "com.android.settingslib.devicestate.settings": "Device State Settings",
    "com.android.sharedstoragebackup": "Shared Storage Backup",
    "com.android.shell": "Shell",
    "com.android.simappdialog": "SIM App Dialog",
    "com.android.soundpicker": "Sound Picker",
    "com.android.statementservice": "Intent Filter Verification Service",
    "com.android.storagemanager": "Storage Manager",
    "com.android.stk": "SIM Toolkit",
    "com.android.stk2": "SIM Toolkit 2",
    "com.android.systemui": "System UI",
    "com.android.terminal": "Terminal",
    "com.android.traceur": "System Tracing",
    "com.android.vending": "Google Play Store",
    "com.android.vpndialogs": "VPN Dialogs",
    "com.android.wallpaper.livepicker": "Live Wallpaper Picker",
    "com.android.wallpapercropper": "Wallpaper Cropper",
    "com.android.webview": "Android WebView",
    "com.android.wifi": "Wi-Fi Framework",
    "com.android.wifi.resources": "Wi-Fi Resources",
    "com.android.wirelesscharging": "Wireless Charging",
    "com.android.wlan.hal": "WLAN HAL",

    # ── Google ───────────────────────────────────────────────────────────────
    "com.google.android.accessibility.soundamplifier": "Sound Amplifier",
    "com.google.android.ambient.sensing": "Ambient Sensing",
    "com.google.android.apps.adm": "Android Device Manager",
    "com.google.android.apps.ads.ashbird": "Google Ads",
    "com.google.android.apps.assistive_tech": "Lookout",
    "com.google.android.apps.automotive.media": "Automotive Media",
    "com.google.android.apps.backup": "Backup Transport",
    "com.google.android.apps.bard": "Google Gemini",
    "com.google.android.apps.camera": "Google Camera",
    "com.google.android.apps.chromecast.app": "Google Home",
    "com.google.android.apps.cloudprint": "Cloud Print",
    "com.google.android.apps.combinedcontacts": "Google Contacts",
    "com.google.android.apps.docs": "Google Docs",
    "com.google.android.apps.docs.editors.docs": "Google Docs",
    "com.google.android.apps.docs.editors.sheets": "Google Sheets",
    "com.google.android.apps.docs.editors.slides": "Google Slides",
    "com.google.android.apps.enterprise.auth": "Android Enterprise Auth",
    "com.google.android.apps.filemanager": "Files by Google",
    "com.google.android.apps.fitness": "Google Fit",
    "com.google.android.apps.fonts": "Google Fonts",
    "com.google.android.apps.googleassistant": "Google Assistant",
    "com.google.android.apps.helprtc": "Google Help",
    "com.google.android.apps.kids.familylink": "Family Link",
    "com.google.android.apps.kids.familystar": "Family Star",
    "com.google.android.apps.location.rp.service": "Location Reporting",
    "com.google.android.apps.magazines": "Google News",
    "com.google.android.apps.maps": "Google Maps",
    "com.google.android.apps.messaging": "Google Messages",
    "com.google.android.apps.motionsense": "Motion Sense",
    "com.google.android.apps.nexuslauncher": "Pixel Launcher",
    "com.google.android.apps.nfc.service": "NFC Service",
    "com.google.android.apps.photos": "Google Photos",
    "com.google.android.apps.pixel.creativeassistant": "Pixel Creative Assistant",
    "com.google.android.apps.podcasts": "Google Podcasts",
    "com.google.android.apps.recorder": "Pixel Recorder",
    "com.google.android.apps.safetyhub": "Safety Hub",
    "com.google.android.apps.screensmarts": "Now Playing",
    "com.google.android.apps.sconeagent": "Device Personalization Services",
    "com.google.android.apps.setupwizard.searchselector": "Search Selector",
    "com.google.android.apps.share": "Shared Album",
    "com.google.android.apps.slides": "Google Slides",
    "com.google.android.apps.subscriptions.red": "Google One",
    "com.google.android.apps.tachyon": "Google Meet",
    "com.google.android.apps.tips": "Pixel Tips",
    "com.google.android.apps.translate": "Google Translate",
    "com.google.android.apps.turbo": "Device Health Services",
    "com.google.android.apps.tycho": "Project Fi (Google Fi)",
    "com.google.android.apps.village.boond": "Boond",
    "com.google.android.apps.walletnfcrel": "Google Wallet",
    "com.google.android.apps.wellbeing": "Digital Wellbeing",
    "com.google.android.apps.work.profile": "Work Profile",
    "com.google.android.apps.youtube.music": "YouTube Music",
    "com.google.android.as": "Android System Intelligence",
    "com.google.android.as.oss": "Android System Intelligence (OSS)",
    "com.google.android.backuptransport": "Google Backup Transport",
    "com.google.android.betterbug": "Better Bug",
    "com.google.android.calendar": "Google Calendar",
    "com.google.android.captiveportallogin": "Captive Portal Login",
    "com.google.android.carrier": "Google Carrier Services",
    "com.google.android.carrier.devicesetup": "Device Setup (Carrier)",
    "com.google.android.carriersetup": "Carrier Setup",
    "com.google.android.cellbroadcastreceiver": "Google Cell Broadcast",
    "com.google.android.cellbroadcastservice": "Google Cell Broadcast Service",
    "com.google.android.configupdater": "Config Updater",
    "com.google.android.contacts": "Google Contacts",
    "com.google.android.deskclock": "Google Clock",
    "com.google.android.devicelockcontroller": "Device Lock Controller",
    "com.google.android.dialer": "Google Phone",
    "com.google.android.documentsui": "Files",
    "com.google.android.downloadmanager": "Google Download Manager",
    "com.google.android.dtsa": "Device Threat Security App",
    "com.google.android.euicc": "Google eUICC",
    "com.google.android.euicc.support": "eUICC Support",
    "com.google.android.ext.services": "Android Services Library",
    "com.google.android.ext.shared": "Android Shared Library",
    "com.google.android.feedback": "Google Feedback",
    "com.google.android.gm": "Gmail",
    "com.google.android.gm.lite": "Gmail Go",
    "com.google.android.gms": "Google Play Services",
    "com.google.android.gmsintegration": "GMS Integration",
    "com.google.android.go.maps": "Maps Go",
    "com.google.android.googlequicksearchbox": "Google Search",
    "com.google.android.gsf": "Google Services Framework",
    "com.google.android.gsf.login": "Google Account Manager",
    "com.google.android.healthconnect.controller": "Health Connect",
    "com.google.android.hotwordenrollment": "Hotword Enrollment",
    "com.google.android.ims": "Google IMS",
    "com.google.android.inputmethod.korean": "Google Korean IME",
    "com.google.android.inputmethod.latin": "Gboard",
    "com.google.android.inputmethod.pinyin": "Google Pinyin Input",
    "com.google.android.keep": "Google Keep",
    "com.google.android.launcher": "Google Launcher",
    "com.google.android.lollipop.notepad": "Notepad",
    "com.google.android.marvin.talkback": "Google TalkBack",
    "com.google.android.mconfigservice": "Mobile Configuration Service",
    "com.google.android.modulemetadata": "Module Metadata",
    "com.google.android.music": "Google Play Music",
    "com.google.android.nearby": "Nearby Share",
    "com.google.android.networkstack": "Network Stack",
    "com.google.android.networkstack.tethering": "Tethering",
    "com.google.android.onetimeinitializer": "One Time Initializer",
    "com.google.android.packageinstaller": "Google Package Installer",
    "com.google.android.paxservice": "PAX Service",
    "com.google.android.permissioncontroller": "Permission Controller",
    "com.google.android.play.games": "Google Play Games",
    "com.google.android.playgames": "Play Games",
    "com.google.android.plus": "Google+",
    "com.google.android.printservice.recommendation": "Print Service Recommendation",
    "com.google.android.projection.gearhead": "Android Auto",
    "com.google.android.safetycenter.resources": "Safety Center Resources",
    "com.google.android.safetynet": "SafetyNet",
    "com.google.android.sdksandbox": "SDK Sandbox",
    "com.google.android.settings.intelligence": "Settings Intelligence",
    "com.google.android.setupwizard": "Google Setup Wizard",
    "com.google.android.soundsearch": "Sound Search",
    "com.google.android.speech.pumpkin": "Speech Services",
    "com.google.android.storagemanager": "Google Storage Manager",
    "com.google.android.syncadapters.calendar": "Google Calendar Sync",
    "com.google.android.syncadapters.contacts": "Google Contacts Sync",
    "com.google.android.tag": "NFC Tags",
    "com.google.android.talk": "Google Hangouts",
    "com.google.android.tts": "Google Text-to-Speech",
    "com.google.android.tv": "Google TV",
    "com.google.android.tv.remote.service": "Android TV Remote Service",
    "com.google.android.tvlauncher": "Google TV Launcher",
    "com.google.android.uiservices.debugtools": "Debug Tools",
    "com.google.android.uwb": "UWB Service",
    "com.google.android.videos": "Google Play Movies",
    "com.google.android.volta": "Battery Historian",
    "com.google.android.webview": "Android System WebView",
    "com.google.android.wifi.resources": "Wi-Fi Resources (Google)",
    "com.google.android.wlan.hal": "WLAN HAL (Google)",
    "com.google.android.youtube": "YouTube",
    "com.google.mainline.telemetry": "Mainline Telemetry",
    "com.google.pixel.camera.hal": "Pixel Camera HAL",
    "com.google.usb.permission": "USB Permission",

    # ── Samsung (com.samsung.*, com.sec.*, com.samsungims, etc.) ─────────────
    "com.samsung.android.allshare.service.fileshare": "Samsung AllShare File Share",
    "com.samsung.android.allshare.service.mediashare": "Samsung AllShare Media Share",
    "com.samsung.android.app.aodservice": "Always On Display Service",
    "com.samsung.android.app.cameraassistant": "Camera Assistant",
    "com.samsung.android.app.clipboardedge": "Clipboard Edge",
    "com.samsung.android.app.cocktailbarservice": "Edge Panel",
    "com.samsung.android.app.dofviewer": "Live Focus Viewer",
    "com.samsung.android.app.galaxyfinder": "Galaxy Finder",
    "com.samsung.android.app.galaxystore": "Galaxy Store",
    "com.samsung.android.app.groupcast": "Group Cast",
    "com.samsung.android.app.ledcover": "LED Cover",
    "com.samsung.android.app.ledcoverdream": "LED Cover Dream",
    "com.samsung.android.app.livesetup": "Live Focus Setup",
    "com.samsung.android.app.mirrorlink": "MirrorLink",
    "com.samsung.android.app.notes": "Samsung Notes",
    "com.samsung.android.app.omcagent": "OMC Agent",
    "com.samsung.android.app.personalizationservice": "Personalization Service",
    "com.samsung.android.app.readingglass": "Reading Glass",
    "com.samsung.android.app.remoteservice": "Samsung Remote Service",
    "com.samsung.android.app.routines": "Samsung Routines",
    "com.samsung.android.app.sbrowseredge": "Samsung Internet Edge",
    "com.samsung.android.app.settings.bixby": "Bixby Settings",
    "com.samsung.android.app.spage": "Samsung Free",
    "com.samsung.android.app.sreminder": "Samsung Reminder",
    "com.samsung.android.app.telephonyui": "Samsung Telephony UI",
    "com.samsung.android.app.tips": "Samsung Tips",
    "com.samsung.android.app.tws.setting": "Galaxy Buds Settings",
    "com.samsung.android.app.updatecenter": "Samsung Update Center",
    "com.samsung.android.app.watchmanagergallery": "Galaxy Watch Manager",
    "com.samsung.android.app.withtv": "Samsung With TV",
    "com.samsung.android.aremoji": "AR Emoji",
    "com.samsung.android.arzone": "AR Zone",
    "com.samsung.android.audio.axp": "Samsung Audio",
    "com.samsung.android.authfw": "Authentication Framework",
    "com.samsung.android.auto.easysettings": "Samsung Auto Easy Settings",
    "com.samsung.android.aware.service": "Samsung Aware Service",
    "com.samsung.android.bbc.bbcagent": "BBC Agent",
    "com.samsung.android.beaconmanager": "Beacon Manager",
    "com.samsung.android.bigconfupdater": "Samsung Config Updater",
    "com.samsung.android.bixby": "Bixby",
    "com.samsung.android.bixby.agent": "Bixby Voice",
    "com.samsung.android.bixby.agent.dummy": "Bixby Agent Dummy",
    "com.samsung.android.bixby.es.fantasylogger": "Bixby Logger",
    "com.samsung.android.bixby.service": "Bixby Service",
    "com.samsung.android.bixby.wakeup": "Bixby Wakeup",
    "com.samsung.android.bixbyvision.framework": "Bixby Vision",
    "com.samsung.android.bluetooth.localupdater": "Bluetooth Updater",
    "com.samsung.android.callbgprovider": "Call Background Provider",
    "com.samsung.android.camera.camerax.provider": "CameraX Provider",
    "com.samsung.android.channelmanager": "Channel Manager",
    "com.samsung.android.cidmanager": "CID Manager",
    "com.samsung.android.clipboardsaveservice": "Clipboard Save",
    "com.samsung.android.cmfa.framework": "CMFA Framework",
    "com.samsung.android.cognitivexperience": "Cognitive Experience",
    "com.samsung.android.contacts": "Samsung Contacts",
    "com.samsung.android.content.provider.suggestions": "Content Suggestions",
    "com.samsung.android.da.daagent": "Samsung DA Agent",
    "com.samsung.android.dcs": "Samsung DCS",
    "com.samsung.android.dde": "Samsung DDE",
    "com.samsung.android.dynamiclock": "Dynamic Lock Screen",
    "com.samsung.android.easysetup": "Samsung Easy Setup",
    "com.samsung.android.email.provider": "Samsung Email Provider",
    "com.samsung.android.enterprise.push": "Samsung Knox Push",
    "com.samsung.android.fast.edge": "Fast Edge Panel",
    "com.samsung.android.featurerequester": "Feature Requester",
    "com.samsung.android.fido": "Samsung FIDO",
    "com.samsung.android.fmm": "Find My Mobile",
    "com.samsung.android.forest": "Samsung Digital Wellbeing",
    "com.samsung.android.galaxywearable": "Galaxy Wearable",
    "com.samsung.android.game.gamehome": "Game Launcher",
    "com.samsung.android.game.gametools": "Game Booster",
    "com.samsung.android.game.gos": "Game Optimizing Service",
    "com.samsung.android.game.neonstudio": "Neon Studio",
    "com.samsung.android.globaldownloadapp": "Global Download App",
    "com.samsung.android.globalsetup": "Samsung Global Setup",
    "com.samsung.android.gru": "Galaxy Resource Updater",
    "com.samsung.android.health": "Samsung Health",
    "com.samsung.android.health.service": "Samsung Health Service",
    "com.samsung.android.ims": "Samsung IMS",
    "com.samsung.android.incallui": "In-Call UI",
    "com.samsung.android.intelligenceservice": "Samsung Intelligence Service",
    "com.samsung.android.internet.service": "Samsung Internet Service",
    "com.samsung.android.kgclient": "Knox Guard",
    "com.samsung.android.knox.analytics.uploader": "Knox Analytics Uploader",
    "com.samsung.android.knox.attestation": "Knox Attestation",
    "com.samsung.android.knox.containeragent": "Knox Container Agent",
    "com.samsung.android.knox.enrollment": "Knox Enrollment",
    "com.samsung.android.knox.pushmanager": "Knox Push Manager",
    "com.samsung.android.lool": "Samsung Look",
    "com.samsung.android.mateagent": "Mate Agent",
    "com.samsung.android.mcfserver": "MCF Server",
    "com.samsung.android.messaging": "Samsung Messages",
    "com.samsung.android.mobileservice": "Samsung Mobile Services",
    "com.samsung.android.model.download.service": "Model Download Service",
    "com.samsung.android.motionlaunchapp": "Motion Launch",
    "com.samsung.android.nfc": "Samsung NFC",
    "com.samsung.android.oneconnect": "SmartThings",
    "com.samsung.android.pagesharing": "Samsung Page Sharing",
    "com.samsung.android.penservice": "S Pen Service",
    "com.samsung.android.phone": "Samsung Phone",
    "com.samsung.android.platformsvc": "Platform Service",
    "com.samsung.android.plugin.underwater": "Underwater Mode Plugin",
    "com.samsung.android.privatesharing": "Private Sharing",
    "com.samsung.android.qr.service": "QR Code Service",
    "com.samsung.android.rcs": "Samsung RCS",
    "com.samsung.android.rubin.app": "Rubin Data Reporting",
    "com.samsung.android.safetyinformation": "Safety Information",
    "com.samsung.android.samsung.pay.service": "Samsung Pay Service",
    "com.samsung.android.samsungpay.gear": "Samsung Pay on Gear",
    "com.samsung.android.sbrowser": "Samsung Internet",
    "com.samsung.android.sdk.handwriting": "Samsung Handwriting SDK",
    "com.samsung.android.securitylogagent": "Security Log Agent",
    "com.samsung.android.service.airview": "Air View Service",
    "com.samsung.android.service.desktopmode": "Samsung Desktop Mode",
    "com.samsung.android.service.peoplestripe": "People Edge",
    "com.samsung.android.setting.multiring": "Samsung Multi Ring",
    "com.samsung.android.settings.bixby": "Bixby for Settings",
    "com.samsung.android.sharedcloud": "Shared Cloud Service",
    "com.samsung.android.share.crash": "Samsung Share Crash Handler",
    "com.samsung.android.shortcutbackupservice": "Shortcut Backup",
    "com.samsung.android.simcardmanager": "SIM Card Manager",
    "com.samsung.android.slinkservice": "Samsung Link Service",
    "com.samsung.android.smartcallprovider": "Smart Call Provider",
    "com.samsung.android.smartmirroring": "Smart Mirroring",
    "com.samsung.android.smartsuggestionsengine": "Smart Suggestions Engine",
    "com.samsung.android.sni.generic": "Samsung SNI",
    "com.samsung.android.sservice": "Samsung Service",
    "com.samsung.android.stickercenter": "Sticker Center",
    "com.samsung.android.stickerprocess": "Sticker Process",
    "com.samsung.android.system.theme": "Samsung System Theme",
    "com.samsung.android.tadownloader": "Theme & AOD Downloader",
    "com.samsung.android.themecenter": "Samsung Theme Center",
    "com.samsung.android.themestore": "Galaxy Themes Store",
    "com.samsung.android.toolbox": "Samsung Toolbox",
    "com.samsung.android.ucs": "Universal Call Service",
    "com.samsung.android.ucsfallback": "UCS Fallback",
    "com.samsung.android.universalswitch": "Universal Switch",
    "com.samsung.android.update": "Samsung Update",
    "com.samsung.android.usb.service": "Samsung USB Service",
    "com.samsung.android.visionarapps": "Vision AR",
    "com.samsung.android.vocalizer": "Vocalizer TTS",
    "com.samsung.android.voiceserviceplatform": "Voice Service Platform",
    "com.samsung.android.vtcamerasettings": "Video Call Camera Settings",
    "com.samsung.android.weather": "Samsung Weather",
    "com.samsung.android.wifi.resources": "Wi-Fi Resources (Samsung)",
    "com.samsung.android.wifi.softap.resources": "Wi-Fi Softap Resources",
    "com.samsung.android.wlantest": "WLAN Test",
    "com.samsung.android.woodnet.agent": "WoodNet Agent",
    "com.samsung.app.clockpack": "Samsung Clock",
    "com.samsung.app.newtrim": "Video Trimmer",
    "com.samsung.content.provider.suggestions": "Content Suggestions",
    "com.samsung.crane": "Samsung Crane",
    "com.samsung.desktopsystemui": "Desktop System UI",
    "com.samsung.featurizer": "Samsung Featurizer",
    "com.samsung.ipservice": "IP Service",
    "com.samsung.location.provider": "Samsung Location Provider",
    "com.samsung.samsungpassautofill": "Samsung Pass AutoFill",
    "com.samsung.samsungpos": "Samsung POS",
    "com.sec.android.app.billing": "Samsung Billing",
    "com.sec.android.app.bluetoothtest": "Bluetooth Test",
    "com.sec.android.app.camera": "Samsung Camera",
    "com.sec.android.app.chromecustomizations": "Chrome Customizations",
    "com.sec.android.app.clockpackage": "Samsung Clock",
    "com.sec.android.app.cplayer": "Samsung Music",
    "com.sec.android.app.dictomatic": "Samsung Dictionary",
    "com.sec.android.app.dmclient": "DM Client",
    "com.sec.android.app.dressroom": "Dress Room",
    "com.sec.android.app.dtp": "DTP Service",
    "com.sec.android.app.emailsettings": "Email Settings",
    "com.sec.android.app.factorykeystring": "Factory Key String",
    "com.sec.android.app.fm": "FM Radio",
    "com.sec.android.app.gatewayservice": "Gateway Service",
    "com.sec.android.app.kidshome": "Samsung Kids",
    "com.sec.android.app.launcher": "Samsung Launcher",
    "com.sec.android.app.minimode": "Mini Mode",
    "com.sec.android.app.myfiles": "Samsung My Files",
    "com.sec.android.app.mypage": "My Page",
    "com.sec.android.app.naviweather": "Navigation Weather",
    "com.sec.android.app.personalization": "Samsung Personalization",
    "com.sec.android.app.photoeditor": "Photo Editor",
    "com.sec.android.app.popupuireceiver": "Popup UI Receiver",
    "com.sec.android.app.ringtone": "Samsung Ringtone",
    "com.sec.android.app.sbrowseredge": "Samsung Internet Edge",
    "com.sec.android.app.sbrowserhome": "Samsung Internet Home",
    "com.sec.android.app.screenrecorder": "Screen Recorder",
    "com.sec.android.app.secsetupwizard": "Samsung Setup Wizard",
    "com.sec.android.app.servicemodeapp": "Service Mode",
    "com.sec.android.app.setupwizard": "Samsung Setup Wizard",
    "com.sec.android.app.shealth": "Samsung Health",
    "com.sec.android.app.smartreminder": "Smart Reminder",
    "com.sec.android.app.sns": "Samsung Social Hub",
    "com.sec.android.app.soundpicker": "Sound Picker",
    "com.sec.android.app.spamanager": "Spam Manager",
    "com.sec.android.app.specialfeatures": "Special Features",
    "com.sec.android.app.taskmanager": "Task Manager",
    "com.sec.android.app.translation": "Samsung Translation",
    "com.sec.android.app.twdvfs": "TwDvfs",
    "com.sec.android.app.videoplayer": "Samsung Video Player",
    "com.sec.android.app.voicenote": "Samsung Voice Recorder",
    "com.sec.android.app.wfdbroker": "Wi-Fi Direct Broker",
    "com.sec.android.app.wzmanager": "WzManager",
    "com.sec.android.app.zdm": "ZDM",
    "com.sec.android.daemonapp": "Samsung Daemon App",
    "com.sec.android.easyMover": "Smart Switch",
    "com.sec.android.gallery3d": "Samsung Gallery",
    "com.sec.android.inputmethod.latin": "Samsung Keyboard",
    "com.sec.android.mimage.photoretouching": "Photo Retouching",
    "com.sec.android.nearby": "Samsung Nearby Share",
    "com.sec.android.preloadinstaller": "Preload Installer",
    "com.sec.android.provider.badge": "Badge Provider",
    "com.sec.android.provider.dlna": "DLNA Provider",
    "com.sec.android.provider.emergencyalerts": "Emergency Alerts",
    "com.sec.android.provider.logsprovider": "Log Provider",
    "com.sec.android.provider.sns": "SNS Provider",
    "com.sec.android.smartfaceservice": "Smart Face Service",
    "com.sec.android.widgetapp.webmanual": "Web Manual",
    "com.sec.dolby.da": "Dolby Audio",
    "com.sec.enterprise.knox.cloudmdm.smdms": "Knox Cloud MDM",
    "com.sec.location.nldnlpservice": "Samsung Location Service",
    "com.sec.location.nsflp2": "Samsung Location Service 2",
    "com.sec.phone": "Samsung Phone Service",
    "com.sec.spp.sync": "Samsung Sync",
    "com.sec.voiceassist": "Voice Assist",
    "com.samsungims": "Samsung IMS Service",

    # ── Xiaomi / MIUI ────────────────────────────────────────────────────────
    "com.miui.analytics": "MIUI Analytics",
    "com.miui.antispam": "MIUI Anti-Spam",
    "com.miui.audiomonitor": "Audio Monitor",
    "com.miui.backup": "MIUI Backup",
    "com.miui.cloudbackup": "MIUI Cloud Backup",
    "com.miui.cloudservice": "Xiaomi Cloud Service",
    "com.miui.compass": "Xiaomi Compass",
    "com.miui.contentextension": "Content Extension",
    "com.miui.coreservice": "MIUI Core Service",
    "com.miui.daemon": "MIUI Daemon",
    "com.miui.dataenabled": "Data Enable Service",
    "com.miui.face": "Face Unlock",
    "com.miui.freeform": "Freeform (Split Screen)",
    "com.miui.guardprovider": "Security Guard Provider",
    "com.miui.hybrid": "MIUI Hybrid",
    "com.miui.hybrid.accessory": "MIUI Hybrid Accessory",
    "com.miui.klo.bugreport": "KLO Bug Report",
    "com.miui.lbe.service": "LBE Security Master",
    "com.miui.lpa": "LPA Service",
    "com.miui.maml.view": "MIUI MAML View",
    "com.miui.mediaeditor": "MIUI Media Editor",
    "com.miui.msa.global": "MIUI System Ads (Global)",
    "com.miui.notification": "MIUI Notifications",
    "com.miui.packageinstaller": "MIUI Package Installer",
    "com.miui.permcenter": "MIUI Permission Center",
    "com.miui.player": "MIUI Music Player",
    "com.miui.rom": "MIUI ROM Updater",
    "com.miui.screenrecorder": "MIUI Screen Recorder",
    "com.miui.securityadd": "MIUI Security Addition",
    "com.miui.securitycenter": "MIUI Security Center",
    "com.miui.settings": "MIUI Settings",
    "com.miui.system": "MIUI System Service",
    "com.miui.systemAdSolution": "MIUI System Ad Solution",
    "com.miui.systemui.plugin": "MIUI SystemUI Plugin",
    "com.miui.touchassistant": "Touch Assistant",
    "com.miui.translation.kingsoft": "Kingsoft Translation",
    "com.miui.translation.youdao": "Youdao Translation",
    "com.miui.translationservice": "MIUI Translation Service",
    "com.miui.videoplayer": "MIUI Video Player",
    "com.miui.weather2": "MIUI Weather",
    "com.miui.wmsvc": "WMS Service",
    "com.miui.yellowpage": "Yellow Pages",
    "com.xiaomi.account": "Xiaomi Account",
    "com.xiaomi.aireco": "AirEco Service",
    "com.xiaomi.bluetooth": "Xiaomi Bluetooth",
    "com.xiaomi.discover": "Xiaomi Discover",
    "com.xiaomi.finddevice": "Find Device",
    "com.xiaomi.glgm": "Xiaomi GLGM",
    "com.xiaomi.joyose": "Joyose (Xiaomi Gaming)",
    "com.xiaomi.k33b.devicesetup": "Device Setup (POCO)",
    "com.xiaomi.market": "Xiaomi Market",
    "com.xiaomi.metoknlp": "MetokNLP",
    "com.xiaomi.midrop": "ShareMe (Mi Drop)",
    "com.xiaomi.miplay_client": "Mi Play",
    "com.xiaomi.mipush.sdk": "Xiaomi Push SDK",
    "com.xiaomi.passport": "Xiaomi Passport",
    "com.xiaomi.payment": "Mi Pay",
    "com.xiaomi.powerchecker": "Power Checker",
    "com.xiaomi.scanner": "Xiaomi Scanner",
    "com.xiaomi.simactivate.service": "SIM Activate Service",
    "com.xiaomi.smarthome": "Mi Smart Home",
    "com.xiaomi.xmsf.push": "XMSF Push",
    "org.mipay.android.manager": "MiPay Manager",

    # ── Huawei / Honor ───────────────────────────────────────────────────────
    "com.huawei.android.launcher": "Huawei Launcher",
    "com.huawei.android.totemweather": "Huawei Weather",
    "com.huawei.appmarket": "Huawei AppGallery",
    "com.huawei.assistant": "Huawei Assistant",
    "com.huawei.bd": "Behavior Data Analytics",
    "com.huawei.browser": "Huawei Browser",
    "com.huawei.camera": "Huawei Camera",
    "com.huawei.contactscamcard": "Business Card Scanner",
    "com.huawei.health": "Huawei Health",
    "com.huawei.hitouch": "HiTouch",
    "com.huawei.hiview": "HiView Analytics",
    "com.huawei.hiskytone": "Huawei Ringtones",
    "com.huawei.hivoice": "HiVoice",
    "com.huawei.hwid": "Huawei ID",
    "com.huawei.hwireader": "Huawei Reader",
    "com.huawei.intelligent": "Huawei Intelligent Assistance",
    "com.huawei.iReader": "iReader",
    "com.huawei.lbs": "Huawei Location Service",
    "com.huawei.livewallpaper": "Huawei Live Wallpaper",
    "com.huawei.mediatransform.usbshare": "USB Share",
    "com.huawei.mmitest": "MMI Test",
    "com.huawei.music": "Huawei Music",
    "com.huawei.nearby": "Huawei Nearby Service",
    "com.huawei.photos": "Huawei Photos",
    "com.huawei.phoneservice": "Huawei Phone Service",
    "com.huawei.privacysec": "Privacy Security",
    "com.huawei.pushagent": "Huawei Push Agent",
    "com.huawei.se": "Huawei SE",
    "com.huawei.search": "Huawei Search",
    "com.huawei.systemmanager": "Phone Manager",
    "com.huawei.tips": "Huawei Tips",
    "com.huawei.wallet": "Huawei Wallet",
    "com.huawei.works": "Huawei Works",
    "com.hihonor.android.launcher": "Honor Launcher",
    "com.hihonor.appmarket": "Honor AppGallery",
    "com.hihonor.health": "Honor Health",
    "com.hihonor.id": "Honor ID",

    # ── OnePlus / OxygenOS ───────────────────────────────────────────────────
    "com.oneplus.account": "OnePlus Account",
    "com.oneplus.applocker": "OnePlus App Locker",
    "com.oneplus.audioprofile": "OnePlus Audio Profile",
    "com.oneplus.auroraservice": "OnePlus Aurora Service",
    "com.oneplus.backuprestore": "OnePlus Backup & Restore",
    "com.oneplus.battery.batteryhelper": "OnePlus Battery Helper",
    "com.oneplus.brickmode": "Brick Mode (Focus Mode)",
    "com.oneplus.camera": "OnePlus Camera",
    "com.oneplus.clipboard": "OnePlus Clipboard",
    "com.oneplus.coloros.flashpay": "FlashPay",
    "com.oneplus.connect": "OnePlus Connect",
    "com.oneplus.desktopmode": "OnePlus Desktop Mode",
    "com.oneplus.dolby": "Dolby Atmos (OnePlus)",
    "com.oneplus.dx": "OnePlus DX",
    "com.oneplus.filemanager": "OnePlus File Manager",
    "com.oneplus.fingerprint": "OnePlus Fingerprint",
    "com.oneplus.gallery": "OnePlus Gallery",
    "com.oneplus.gamespace": "OnePlus Game Space",
    "com.oneplus.hotpocket": "HotPocket",
    "com.oneplus.launcher": "OnePlus Launcher",
    "com.oneplus.logkit": "OnePlus Log Kit",
    "com.oneplus.music": "OnePlus Music",
    "com.oneplus.onepluslauncher": "OnePlus Launcher",
    "com.oneplus.opbackup": "OnePlus Backup",
    "com.oneplus.oplauncher": "OnePlus Launcher",
    "com.oneplus.personalassistant": "OnePlus Personal Assistant",
    "com.oneplus.screenrecord": "OnePlus Screen Recorder",
    "com.oneplus.settings": "OnePlus Settings",
    "com.oneplus.setupwizard": "OnePlus Setup Wizard",
    "com.oneplus.sharetransfer": "OnePlus Share Transfer",
    "com.oneplus.switch": "OnePlus Switch",
    "com.oneplus.tips": "OnePlus Tips",
    "com.oneplus.wallpaperpicker": "OnePlus Wallpaper Picker",
    "com.oneplus.weather": "OnePlus Weather",
    "com.oneplus.workspaces": "OnePlus Work Spaces",
    "com.oplus.ostart": "OPPO Start Service",

    # ── OPPO / ColorOS / Realme ───────────────────────────────────────────────
    "com.coloros.assistantscreen": "OPPO Assistant Screen",
    "com.coloros.backuprestore": "ColorOS Backup & Restore",
    "com.coloros.browser": "ColorOS Browser",
    "com.coloros.calendar": "ColorOS Calendar",
    "com.coloros.camera": "ColorOS Camera",
    "com.coloros.childrenspace": "Kids Space",
    "com.coloros.desktopicons.theme": "Desktop Icons Theme",
    "com.coloros.dialer": "ColorOS Phone",
    "com.coloros.filemanager": "ColorOS File Manager",
    "com.coloros.flashpay": "Flash Pay",
    "com.coloros.gallery": "ColorOS Gallery",
    "com.coloros.gamespace": "OPPO Game Space",
    "com.coloros.healthservice": "ColorOS Health Service",
    "com.coloros.launcher": "ColorOS Launcher",
    "com.coloros.mcs": "Mobile Cloud Service",
    "com.coloros.messenger": "ColorOS Messages",
    "com.coloros.nearbyservice": "OPPO Nearby Service",
    "com.coloros.oshare": "O Share (ColorOS)",
    "com.coloros.phone": "OPPO Phone",
    "com.coloros.phonemanager": "Phone Manager (OPPO)",
    "com.coloros.scenariorecognition": "Scenario Recognition",
    "com.coloros.securepay": "Secure Pay",
    "com.coloros.setupwizard": "ColorOS Setup Wizard",
    "com.coloros.smartpay": "Smart Pay",
    "com.coloros.store": "OPPO App Market",
    "com.coloros.themestore": "OPPO Theme Store",
    "com.coloros.weather": "ColorOS Weather",
    "com.heytap.browser": "HeyTap Browser",
    "com.heytap.cloud": "HeyTap Cloud",
    "com.heytap.emailmaster": "Email Master (HeyTap)",
    "com.heytap.health": "HeyTap Health",
    "com.heytap.luckymoney": "Lucky Money (OPPO)",
    "com.heytap.market": "OPPO App Market",
    "com.heytap.mcs": "HeyTap Mobile Cloud",
    "com.heytap.pictorial": "HeyTap Pictorial",
    "com.heytap.yoli": "OPPO Yoli",
    "com.realme.account": "Realme Account",
    "com.realme.backup": "Realme Backup",
    "com.realme.browser": "Realme Browser",
    "com.realme.camera": "Realme Camera",
    "com.realme.community": "Realme Community",
    "com.realme.dialer": "Realme Phone",
    "com.realme.filemanager": "Realme File Manager",
    "com.realme.gallery": "Realme Gallery",
    "com.realme.gamespace": "Realme Game Space",
    "com.realme.launcher": "Realme Launcher",
    "com.realme.market": "Realme App Market",
    "com.realme.ota": "Realme OTA Updater",
    "com.realme.packageinstaller": "Realme Package Installer",
    "com.realme.setupwizard": "Realme Setup Wizard",
    "com.realme.store": "Realme Store",
    "com.realme.weather": "Realme Weather",

    # ── Motorola ──────────────────────────────────────────────────────────────
    "com.motorola.actions": "Moto Actions",
    "com.motorola.android.bugreporter": "Moto Bug Reporter",
    "com.motorola.appdirectedsmssdk": "App Directed SMS SDK",
    "com.motorola.audioeffect": "Audio Effects (Motorola)",
    "com.motorola.brapps": "Moto Brazil Apps",
    "com.motorola.ccc.cellular": "Cellular Config",
    "com.motorola.coresettings": "Motorola Core Settings",
    "com.motorola.devicehelp": "Moto Device Help",
    "com.motorola.dialer": "Moto Phone",
    "com.motorola.dispatcher": "Moto Dispatcher",
    "com.motorola.drm": "Motorola DRM",
    "com.motorola.ecc": "Emergency Call Companion",
    "com.motorola.esdservice": "ESD Service",
    "com.motorola.faceunlock": "Moto Face Unlock",
    "com.motorola.filemanager": "Moto File Manager",
    "com.motorola.frameworkext": "Motorola Framework Extensions",
    "com.motorola.gallery3d": "Moto Gallery",
    "com.motorola.genie": "Moto Genie",
    "com.motorola.gestures.module": "Moto Gestures",
    "com.motorola.helpwidget": "Help Widget",
    "com.motorola.launcher3": "Moto Launcher",
    "com.motorola.lpa.outofbox": "Motorola LPA",
    "com.motorola.migrate": "Moto Migrate",
    "com.motorola.moto.actions.module": "Moto Actions Module",
    "com.motorola.motocare": "Moto Care",
    "com.motorola.motocit": "Motorola CIT",
    "com.motorola.motodisplay": "Moto Display",
    "com.motorola.motosearch": "Moto Search",
    "com.motorola.motosettings": "Moto Settings",
    "com.motorola.msf": "Motorola MSF",
    "com.motorola.myaccount": "Motorola Account",
    "com.motorola.paydayloans": "Pay Day Loans (Motorola)",
    "com.motorola.penservice": "Moto Pen Service",
    "com.motorola.personalization": "Moto Personalization",
    "com.motorola.predictivekeyboard": "Predictive Keyboard",
    "com.motorola.presence": "Moto Presence",
    "com.motorola.readiness": "Moto Readiness",
    "com.motorola.screenshot": "Moto Screenshot",
    "com.motorola.setconfig": "Motorola Set Config",
    "com.motorola.setups": "Moto Setup",
    "com.motorola.sliders": "Moto Sliders",
    "com.motorola.stylusapp": "Stylus App (Motorola)",
    "com.motorola.tblte.system.service": "TBLTE System Service",
    "com.motorola.targetnotif": "Target Notification",
    "com.motorola.timeweatherwidget": "Time & Weather Widget",
    "com.motorola.touchless": "Moto Voice (Touchless)",
    "com.motorola.userchoice": "User Choice",
    "com.motorola.videocall": "Motorola Video Call",
    "com.motorola.voiceactivation": "Voice Activation",

    # ── LG ───────────────────────────────────────────────────────────────────
    "com.lge.bnr": "LG Bug Reporter",
    "com.lge.broadcast": "LG Broadcast",
    "com.lge.camera": "LG Camera",
    "com.lge.contacts": "LG Contacts",
    "com.lge.dialer": "LG Phone",
    "com.lge.email": "LG Email",
    "com.lge.entunedaemon": "LG Entune Daemon",
    "com.lge.fmradio": "LG FM Radio",
    "com.lge.gameoptimizer": "LG Game Optimizer",
    "com.lge.gallery3d": "LG Gallery",
    "com.lge.gnsslogger": "GNSS Logger",
    "com.lge.launcher3": "LG Home Launcher",
    "com.lge.lgassistant": "LG ThinQ Assistant",
    "com.lge.livezoom": "LG Live Zoom",
    "com.lge.lockscreenwallpaper": "Lock Screen Wallpaper",
    "com.lge.messaging": "LG Messages",
    "com.lge.music": "LG Music",
    "com.lge.pay.service": "LG Pay",
    "com.lge.picasso": "LG Picasso",
    "com.lge.qmemoplus": "QMemo+",
    "com.lge.quickclip": "Quick Clip",
    "com.lge.quickhelp": "LG Quick Help",
    "com.lge.quickremote": "Quick Remote",
    "com.lge.smartworld": "LG SmartWorld",
    "com.lge.smartworld.downloader": "LG SmartWorld Downloader",
    "com.lge.sync": "LG Backup & Sync",
    "com.lge.thinq": "LG ThinQ",
    "com.lge.updatecenter": "LG Update Center",
    "com.lge.videocall": "LG Video Call",
    "com.lge.videoplayer": "LG Video Player",
    "com.lge.wifianalytics": "Wi-Fi Analytics",

    # ── Sony ─────────────────────────────────────────────────────────────────
    "com.sonyericsson.android.camera": "Xperia Camera",
    "com.sonyericsson.android.music": "Xperia Music (Walkman)",
    "com.sonyericsson.android.socialphonebook": "Xperia Contacts",
    "com.sonyericsson.conversations": "Xperia Messages",
    "com.sonyericsson.home": "Xperia Home Launcher",
    "com.sonyericsson.music": "Xperia Music",
    "com.sonymobile.android.launcher": "Xperia Launcher",
    "com.sonymobile.android.media": "Media Library (Sony)",
    "com.sonymobile.block": "Spam Filter (Sony)",
    "com.sonymobile.camera": "Xperia Camera",
    "com.sonymobile.cameracommon": "Camera Common (Sony)",
    "com.sonymobile.content.provider.notes": "Notes Provider (Sony)",
    "com.sonymobile.contentsharing": "Content Sharing (Sony)",
    "com.sonymobile.datamonitor": "Data Monitor",
    "com.sonymobile.deskclock": "Xperia Clock",
    "com.sonymobile.dlm": "Device Lifecycle Manager",
    "com.sonymobile.documentviewer": "Xperia Document Viewer",
    "com.sonymobile.draw": "Xperia Draw",
    "com.sonymobile.entertainment.service": "Entertainment Services (Sony)",
    "com.sonymobile.excellencemode": "X-Reality for Mobile",
    "com.sonymobile.featureoptimizer.service": "Feature Optimizer Service",
    "com.sonymobile.gamingfeatures": "Xperia Game Enhancer",
    "com.sonymobile.gmail.xperiaimages": "Xperia Gmail Images",
    "com.sonymobile.locationservice": "Xperia Location Service",
    "com.sonymobile.media": "Media Library",
    "com.sonymobile.music": "Xperia Music",
    "com.sonymobile.music.service": "Music Service (Sony)",
    "com.sonymobile.myxperia": "My Xperia",
    "com.sonymobile.onebonding": "One-Touch Bonding",
    "com.sonymobile.photos": "Xperia Photos (Album)",
    "com.sonymobile.privacy": "Xperia Privacy",
    "com.sonymobile.remoteguard": "Remote Guard",
    "com.sonymobile.scanner": "Xperia Scanner",
    "com.sonymobile.screenrecorder": "Xperia Screen Recorder",
    "com.sonymobile.sidenavigationservice": "Side Navigation Service",
    "com.sonymobile.sidsync": "SID Sync",
    "com.sonymobile.smallapps.sketch": "Sketch (Sony)",
    "com.sonymobile.smallapps.timer": "Timer (Sony)",
    "com.sonymobile.smartar": "Smart AR",
    "com.sonymobile.smartconnect": "Smart Connect",
    "com.sonymobile.smartwatch3.demo": "SmartWatch 3 Demo",
    "com.sonymobile.socialshare": "Social Share (Sony)",
    "com.sonymobile.support": "Xperia Support",
    "com.sonymobile.themes": "Xperia Themes",
    "com.sonymobile.trackingprotection": "Tracking Protection",
    "com.sonymobile.tvsideview": "Video & TV SideView",
    "com.sonymobile.updatesupportnotification": "Update Support Notification",
    "com.sonymobile.videoeditor": "Video Editor (Sony)",

    # ── Nokia / HMD Global ───────────────────────────────────────────────────
    "com.hmdglobal.app.activation": "HMD Activation",
    "com.hmdglobal.app.omacp": "OMA CP (Nokia)",
    "com.hmdglobal.app.setupwizard": "HMD Setup Wizard",
    "com.hmdglobal.camera2": "Nokia Camera",
    "com.hmdglobal.easysetup": "HMD Easy Setup",
    "com.hmdglobal.fmradio": "Nokia FM Radio",
    "com.nokia.phone.ui": "Nokia Phone UI",
    "com.nokia.sounds": "Nokia Sounds",
    "com.nokia.support": "Nokia Support",

    # ── Asus ─────────────────────────────────────────────────────────────────
    "com.asus.asusincallui": "ASUS In-Call UI",
    "com.asus.atd": "ASUS ATD Test",
    "com.asus.calculator": "ASUS Calculator",
    "com.asus.callrecorder": "ASUS Call Recorder",
    "com.asus.camera": "ASUS Camera",
    "com.asus.cnbu": "ASUS CNBU",
    "com.asus.contacts": "ASUS Contacts",
    "com.asus.dm": "ASUS Device Manager",
    "com.asus.email": "ASUS Email",
    "com.asus.filemanager": "ASUS File Manager",
    "com.asus.flashlight": "ASUS Flashlight",
    "com.asus.gallery": "ASUS Gallery",
    "com.asus.gamewidget": "ASUS Game Widget",
    "com.asus.gluptool": "ASUS Glu P Tool",
    "com.asus.inputmethod": "ASUS Input Method",
    "com.asus.launcher": "ASUS Launcher (ZenUI)",
    "com.asus.launcher3": "ASUS Launcher3",
    "com.asus.livescreenservice": "ASUS Live Screen Service",
    "com.asus.loguploader": "ASUS Log Uploader",
    "com.asus.lounge": "ASUS Lounge",
    "com.asus.marketplace": "ASUS Marketplace",
    "com.asus.mobilemanager": "ASUS Mobile Manager",
    "com.asus.musicfx": "ASUS MusicFX",
    "com.asus.myasus": "MyASUS",
    "com.asus.pureswap": "ASUS Pure Swap",
    "com.asus.quickmemo": "ASUS Quick Memo",
    "com.asus.quicksettings": "ASUS Quick Settings",
    "com.asus.registrationapp": "ASUS Registration",
    "com.asus.screensaver": "ASUS Screensaver",
    "com.asus.setupprovider": "ASUS Setup Provider",
    "com.asus.setupwizard": "ASUS Setup Wizard",
    "com.asus.smartdoctor": "ASUS Smart Doctor",
    "com.asus.splendid": "ASUS Splendid (Color Calibration)",
    "com.asus.superresolution": "ASUS Super Resolution",
    "com.asus.systemupdate": "ASUS System Update",
    "com.asus.themes": "ASUS Themes",
    "com.asus.weathertime": "ASUS Weather & Time",
    "com.asus.webstorage": "ASUS WebStorage",
    "com.asus.zenmotion": "ZenMotion",
    "com.asus.zenui.launcher": "ZenUI Launcher",

    # ── ZTE / Nubia ───────────────────────────────────────────────────────────
    "com.nubia.beautycam": "Nubia Beauty Camera",
    "com.nubia.browser": "Nubia Browser",
    "com.nubia.camera": "Nubia Camera",
    "com.nubia.calendar": "Nubia Calendar",
    "com.nubia.launcher": "Nubia Launcher",
    "com.nubia.music": "Nubia Music",
    "com.nubia.service": "Nubia Service",
    "com.nubia.systemservice": "Nubia System Service",
    "com.zte.android.launcher": "ZTE Launcher",
    "com.zte.camera": "ZTE Camera",
    "com.zte.fileexplorer": "ZTE File Explorer",
    "com.zte.guestmode": "ZTE Guest Mode",
    "com.zte.health": "ZTE Health",
    "com.zte.mifavor": "ZTE Mi Favor",
    "com.zte.music": "ZTE Music",
    "com.zte.networkboost": "ZTE Network Boost",
    "com.zte.statistics": "ZTE Statistics",
    "com.zte.zdm": "ZTE Device Manager",

    # ── Vivo / iQOO ───────────────────────────────────────────────────────────
    "com.bbk.account": "Vivo Account",
    "com.bbk.calendar": "Vivo Calendar",
    "com.bbk.camera": "Vivo Camera",
    "com.bbk.contacts": "Vivo Contacts",
    "com.bbk.dialer": "Vivo Phone",
    "com.bbk.email": "Vivo Email",
    "com.bbk.filemanager": "Vivo File Manager",
    "com.bbk.launcher": "Vivo Launcher",
    "com.bbk.messaging": "Vivo Messages",
    "com.bbk.music": "Vivo Music",
    "com.bbk.notes": "Vivo Notes",
    "com.bbk.settings": "Vivo Settings",
    "com.bbk.updater": "Vivo Updater",
    "com.bbk.videoPlayer": "Vivo Video Player",
    "com.bbk.weather": "Vivo Weather",
    "com.vivo.appstore": "Vivo App Store",
    "com.vivo.browser": "Vivo Browser",
    "com.vivo.daemon": "Vivo Daemon",
    "com.vivo.easyshare": "Vivo EasyShare",
    "com.vivo.frameworks.hilauncher": "HiLauncher (Vivo)",
    "com.vivo.gallery": "Vivo Gallery",
    "com.vivo.gamecenter": "Vivo Game Center",
    "com.vivo.internet": "Vivo Internet Service",
    "com.vivo.navservice": "Vivo Navigation Service",
    "com.vivo.pushclient": "Vivo Push Client",
    "com.vivo.screen.recorder": "Vivo Screen Recorder",
    "com.vivo.secspace": "Vivo Secure Space",
    "com.vivo.smartpay": "Vivo Pay",
    "com.vivo.speechengine": "Vivo Speech Engine",
    "com.vivo.systemhelper": "Vivo System Helper",
    "com.vivo.upslide": "Vivo UpSlide",
    "com.vivo.vivobuds": "Vivo TWS Earbuds",
    "com.vivo.weather": "Vivo Weather",

    # ── Meizu ────────────────────────────────────────────────────────────────
    "com.meizu.account": "Flyme Account",
    "com.meizu.assistantservice": "Meizu Assistant Service",
    "com.meizu.base": "Flyme Base Services",
    "com.meizu.browser": "Meizu Browser",
    "com.meizu.cloud": "Flyme Cloud",
    "com.meizu.contacts": "Meizu Contacts",
    "com.meizu.email": "Meizu Email",
    "com.meizu.filemanager": "Meizu File Manager",
    "com.meizu.flyme.health": "Flyme Health",
    "com.meizu.flyme.launcher": "Flyme Launcher",
    "com.meizu.flyme.liveassistant": "Flyme Live Assistant",
    "com.meizu.flyme.pay": "Flyme Pay",
    "com.meizu.gallery": "Meizu Gallery",
    "com.meizu.gamecenter": "Meizu Game Center",
    "com.meizu.media.video": "Meizu Video Player",
    "com.meizu.music": "Meizu Music",
    "com.meizu.note": "Meizu Notes",
    "com.meizu.safe": "Meizu Phone Manager",
    "com.meizu.settings": "Meizu Settings",
    "com.meizu.upgrade": "Meizu OTA Updater",
    "com.meizu.weather": "Meizu Weather",

    # ── Lenovo / ZUI ─────────────────────────────────────────────────────────
    "com.lenovo.anyshare.gps": "SHAREit (Lenovo)",
    "com.lenovo.browser": "Lenovo Browser",
    "com.lenovo.datatransfer": "Data Transfer (Lenovo)",
    "com.lenovo.ideafriend": "IdeaFriend",
    "com.lenovo.lsf.user": "LSF User Service",
    "com.lenovo.motosafe": "Moto Safe (Lenovo)",
    "com.lenovo.shellandroid": "Lenovo Shell",
    "com.lenovo.smart": "Lenovo Smart Engine",
    "com.lenovo.smartcamera": "Lenovo Smart Camera",
    "com.lenovo.vibe": "Lenovo Vibe",
    "com.zui.aiengine": "ZUI AI Engine",
    "com.zui.camera": "ZUI Camera",
    "com.zui.contacts": "ZUI Contacts",
    "com.zui.filemanager": "ZUI File Manager",
    "com.zui.launcher": "ZUI Launcher",
    "com.zui.lenovoweather": "Lenovo Weather",
    "com.zui.market": "ZUI Market",
    "com.zui.messaging": "ZUI Messages",
    "com.zui.notes": "ZUI Notes",
    "com.zui.phone": "ZUI Phone",
    "com.zui.safecenter": "ZUI Safe Center",
    "com.zui.videoeditor": "ZUI Video Editor",
    "com.zui.videoplay": "ZUI Video Player",
    "com.zui.weather": "ZUI Weather",

    # ── TCL / Blackberry ─────────────────────────────────────────────────────
    "com.tcl.android.launcher": "TCL Launcher",
    "com.tcl.coloros.screensaver": "TCL Screensaver",
    "com.tcl.exchange": "TCL Exchange",
    "com.tcl.filemanager": "TCL File Manager",
    "com.tcl.gallery3d": "TCL Gallery",
    "com.tcl.music": "TCL Music",
    "com.tcl.security": "TCL Security",
    "com.tcl.systemupdate": "TCL System Update",
    "com.tct.backup": "TCL Backup",
    "com.tct.browser": "TCL Browser",
    "com.tct.contact": "TCL Contacts",
    "com.tct.dtmonitor": "TCL DT Monitor",
    "com.tct.email": "TCL Email",
    "com.tct.imservice": "TCL IM Service",
    "com.tct.mms": "TCL Messages",
    "com.tct.music": "TCL Music",

    # ── Transsion (Tecno, Infinix, itel) ─────────────────────────────────────
    "com.transsion.aivoice": "Transsion AI Voice",
    "com.transsion.appupdater": "Transsion App Updater",
    "com.transsion.assistantscreen": "Transsion Assistant",
    "com.transsion.camera": "Transsion Camera",
    "com.transsion.carlcare": "Carlcare (Transsion Support)",
    "com.transsion.child": "Kids Mode (Transsion)",
    "com.transsion.contacts": "Transsion Contacts",
    "com.transsion.filemanager": "Transsion File Manager",
    "com.transsion.gamecenter": "Transsion Game Center",
    "com.transsion.hilauncher": "HiLauncher (Transsion)",
    "com.transsion.messaging": "Transsion Messages",
    "com.transsion.music": "Transsion Music",
    "com.transsion.palmax": "PalmX (Transsion)",
    "com.transsion.phonemaster": "Phone Master (Transsion)",
    "com.transsion.screenrecorder": "Transsion Screen Recorder",
    "com.transsion.securityservice": "Security Service (Transsion)",
    "com.transsion.server": "Transsion Server",
    "com.transsion.simcontacts": "Transsion SIM Contacts",
    "com.transsion.siu": "SIU (Transsion)",
    "com.transsion.store": "Transsion App Store",
    "com.transsion.weather": "Transsion Weather",
    "com.itel.marketstore": "itel App Store",
    "com.tecno.launcher3": "Tecno Launcher",
    "com.infinix.launcher": "Infinix Launcher",

    # ── Nothing Phone ────────────────────────────────────────────────────────
    "com.nothing.camera": "Nothing Camera",
    "com.nothing.dialer": "Nothing Phone",
    "com.nothing.launcher": "Nothing Launcher",
    "com.nothing.messages": "Nothing Messages",
    "com.nothing.settings": "Nothing Settings",
    "com.nothing.setup": "Nothing Setup",
    "com.nothing.systemsetting": "Nothing System Setting",
    "com.nothing.weather": "Nothing Weather",

    # ── Carrier apps ─────────────────────────────────────────────────────────
    "com.att.android.attsmartwifi": "AT&T Smart Wi-Fi",
    "com.att.callprotect": "AT&T Call Protect",
    "com.att.device.activation": "AT&T Device Activation",
    "com.att.dh": "AT&T Device Health",
    "com.att.entertainment": "AT&T Entertainment",
    "com.att.iqi": "AT&T IQI",
    "com.att.mobile.android.voicemailstudio": "AT&T Visual Voicemail",
    "com.att.myWireless": "myAT&T",
    "com.att.tv": "AT&T TV",
    "com.metro.zte.adapter": "Metro by T-Mobile Adapter",
    "com.sprint.ce.setupwizard": "Sprint Setup Wizard",
    "com.sprint.messaging": "Sprint Messenger",
    "com.sprint.ms.smf.svp": "Sprint SVP",
    "com.sprint.w.installer": "Sprint Installer",
    "com.t_mobile.tmo.visual": "T-Mobile Visual Voicemail",
    "com.tmobile.comm.android.voice": "T-Mobile Voice",
    "com.tmobile.pr.adapt": "T-Mobile ADAPT",
    "com.tmobile.pr.addons": "T-Mobile Add-Ons",
    "com.tmobile.pr.mytmobile": "T-Mobile App",
    "com.tmobile.tv": "T-Mobile TV",
    "com.verizon.mips.services": "Verizon MIPS",
    "com.verizon.mobilesynergy": "Verizon Mobile Synergy",
    "com.verizon.os": "Verizon OS",
    "com.verizon.photos": "Verizon Photos",
    "com.verizon.services": "Verizon Services",
    "com.verizon.vzwavd": "Verizon AVD",
    "com.vzw.apnservice": "Verizon APN Service",
    "com.vzw.hss.myverizon": "My Verizon",

    # ── Qualcomm / MediaTek chip services ─────────────────────────────────────
    "com.qualcomm.atfwd": "Qualcomm AT Forward",
    "com.qualcomm.cabl": "Content Adaptive Backlight",
    "com.qualcomm.embms": "Qualcomm eMBMS",
    "com.qualcomm.location": "Qualcomm Location",
    "com.qualcomm.qcci.rcsimssettings": "RCS IMS Settings",
    "com.qualcomm.qti.carrierconfigure": "Carrier Configure (QTI)",
    "com.qualcomm.qti.dynamicCV2Xcfg": "Dynamic C-V2X Config",
    "com.qualcomm.qti.gpudrivers.marlin.api30": "Qualcomm GPU Drivers",
    "com.qualcomm.qti.networksetting": "Network Setting (QTI)",
    "com.qualcomm.qti.services.secureui": "Secure UI Service",
    "com.qualcomm.qti.simcontacts": "SIM Contacts (QTI)",
    "com.qualcomm.qti.smcinvokepkgmgr": "SMC Invoke Manager",
    "com.qualcomm.timeservice": "Qualcomm Time Service",
    "com.qualcomm.wfd.legacy": "Wi-Fi Display Legacy",
    "com.mediatek.batterywarning": "MediaTek Battery Warning",
    "com.mediatek.bluetooth": "MediaTek Bluetooth",
    "com.mediatek.capctrl.service": "MediaTek CAP Control",
    "com.mediatek.dm": "MediaTek DM Service",
    "com.mediatek.engineermode": "Engineer Mode (MediaTek)",
    "com.mediatek.gnss": "MediaTek GNSS",
    "com.mediatek.ims": "MediaTek IMS",
    "com.mediatek.lbs.em2": "Location Based Service",
    "com.mediatek.mdmlogs": "MDM Logs",
    "com.mediatek.mms.ext": "MediaTek MMS Extension",
    "com.mediatek.mtklogger": "MTK Logger",
    "com.mediatek.nlpservice": "NLP Service (MediaTek)",
    "com.mediatek.op01.telecom": "OP01 Telecom",
    "com.mediatek.omacp": "OMA CP (MediaTek)",
    "com.mediatek.presence": "MediaTek Presence",
    "com.mediatek.rcs.service": "RCS Service (MediaTek)",
    "com.mediatek.simprocessor": "SIM Processor",
    "com.mediatek.smsreg": "SMS Reg (MediaTek)",
    "com.mediatek.todos": "MediaTek TODO",
    "com.mediatek.voiceunlock": "Voice Unlock (MediaTek)",
    "com.mediatek.wfo.legacy": "WFO Legacy (MediaTek)",

    # ── LineageOS / AOSP custom ROM ──────────────────────────────────────────
    "com.cyanogenmod.eleven": "CyanogenMod Music (Eleven)",
    "com.cyanogenmod.filemanager": "CyanogenMod File Manager",
    "com.cyanogenmod.trebuchet": "CyanogenMod Trebuchet Launcher",
    "org.cyanogenmod.theme.chooser": "CyanogenMod Theme Chooser",
    "org.lineageos.aperture": "LineageOS Camera",
    "org.lineageos.audioeffects": "LineageOS Audio Effects",
    "org.lineageos.backgrounds": "LineageOS Backgrounds",
    "org.lineageos.camelot": "LineageOS PDF Viewer",
    "org.lineageos.etar": "LineageOS Calendar",
    "org.lineageos.glimpse": "LineageOS Gallery",
    "org.lineageos.jelly": "LineageOS Browser",
    "org.lineageos.lineageparts": "LineageOS Parts",
    "org.lineageos.lineagesettings": "LineageOS Settings",
    "org.lineageos.profiles": "LineageOS Profiles",
    "org.lineageos.recorder": "LineageOS Voice Recorder",
    "org.lineageos.setupwizard": "LineageOS Setup Wizard",
    "org.lineageos.twelve": "LineageOS Music",
    "org.lineageos.updater": "LineageOS Updater",
}


# ── Main collector ────────────────────────────────────────────────────────────

def _is_bad_name(name: str) -> bool:
    """Return True if the string is a description, not a human app name."""
    if not name:
        return True
    if len(name) > 55:
        return True
    low = name.lower()
    bad_starts = (
        "it ", "it's", "in the", "has ", "nothing found", "do something",
        "hidden", "rro =", " is the device", "chinese ", "facemoji",
        "com.", "org.", "android.", "this is", "this app",
        "can be", "could be", "may ", "should ", "unsafe",
        "used for", "used to", "related to", "part of ",
        "not sure", "unknown", "unclear", "probably ", "likely ",
        "needed for", "required for", "useless", "quick action", "tws",
        "refers ", "enables ", "provides ", "controls ", "manages ",
        "handles ", "allows ",
    )
    if any(low.startswith(b) for b in bad_starts):
        return True
    # All-lowercase first letter usually means it's a description fragment
    if name[0].islower() and len(name) > 5:
        return True
    # String that IS the package name (e.g. "com.foo.bar")
    if "." in name and name.replace(".", "").replace("_", "").isalnum():
        return True
    # Device codename sentences
    if " is the device codename" in low:
        return True
    return False


def collect(output_path: str | None = None, verbose: bool = True) -> dict[str, str]:
    result: dict[str, str] = {}

    log = print if verbose else lambda *a: None

    log("=" * 60)
    log("ADB Manager — Package Name Database Collector")
    log("=" * 60)

    # Remote sources
    remote_entries = load_uad_ng(result)
    remote_entries += load_muntashir_akon(result)

    # Refuse to overwrite a good database with nothing when the network is down.
    if remote_entries == 0:
        raise RuntimeError(
            "Could not download any package lists (no internet access?). "
            "Existing database left unchanged."
        )

    # Inline packages (override empties, don't overwrite good names)
    log("Merging inline vendor package list...")
    inline_added = 0
    for pkg, name in INLINE_PACKAGES.items():
        if pkg not in result or not result[pkg]:
            result[pkg] = name
            inline_added += 1
        # Only override if our inline name looks better (shorter = more precise)
        elif name and len(name) < len(result[pkg]):
            result[pkg] = name
    log(f"  ✓  {len(INLINE_PACKAGES):,} inline packages ({inline_added:,} new)")

    # Post-process: clear names that are descriptions, not names
    log("Cleaning up description-as-name entries...")
    cleared = 0
    for k in list(result.keys()):
        if _is_bad_name(result[k]):
            result[k] = ""
            cleared += 1
    log(f"  ✓  Cleared {cleared:,} low-quality entries")

    # Merge the existing database so locally harvested / previously fetched
    # names are never lost when the remote lists change.
    out = Path(output_path) if output_path else Path(__file__).parent / "data" / "packages.json"
    merged = 0
    try:
        with open(out, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if isinstance(existing, dict):
            for pkg, name in existing.items():
                if not isinstance(pkg, str) or not isinstance(name, str):
                    continue
                if pkg not in result:
                    result[pkg] = name
                    merged += 1
                elif not result[pkg] and name:
                    result[pkg] = name
                    merged += 1
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        log(f"  !  Could not read existing database ({e}); skipping merge")
    if merged:
        log(f"  ✓  Kept {merged:,} existing entries")

    # Final stats
    named = {k: v for k, v in result.items() if v}
    log(f"\n{'='*60}")
    log(f"Total unique packages : {len(result):,}")
    log(f"With human names      : {len(named):,}")
    log(f"Without names         : {len(result) - len(named):,}")
    log(f"{'='*60}\n")

    # Save
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
    log(f"Saved → {out}")
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the ADB Manager package name database.")
    parser.add_argument("--output", "-o", default=None, help="Output path (default: data/packages.json)")
    args = parser.parse_args()
    try:
        collect(output_path=args.output)
    except RuntimeError as e:
        print(f"Error: {e}")
        raise SystemExit(1) from None
