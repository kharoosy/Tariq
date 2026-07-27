# Tariq – WhatsApp Sticker Creator

An Android application that lets you create WhatsApp sticker packs from images stored on your device.

## Features

- **Pick images from device storage** – supports single or multi-select via the system image picker.
- **Automatic conversion** – selected images are resized to 512 × 512 and encoded as WebP (WhatsApp's required format); a 96 × 96 tray icon is generated automatically.
- **Sticker pack management** – packs are stored in the app's internal storage and listed on the main screen.
- **One-tap WhatsApp integration** – tap *Add to WhatsApp* on any pack to install it directly.
- **Supports Android 5.0 (API 21) and above**, including the granular media permissions introduced in Android 13.

## How it works

WhatsApp discovers sticker packs through a [Content Provider](https://developer.android.com/guide/topics/providers/content-providers).  
`StickerContentProvider` exposes the following URI scheme:

| URI | Description |
|-----|-------------|
| `content://{authority}/metadata` | All sticker packs (metadata) |
| `content://{authority}/metadata/{id}` | Single pack metadata |
| `content://{authority}/stickers/{id}` | Sticker list for a pack |
| `content://{authority}/stickers_asset/{id}/{file}` | Raw sticker image |
| `content://{authority}/tray/{id}` | Tray icon image |

Where `{authority}` = `com.tariq.whatsappstickers.stickercontentprovider`.

## Building

**Prerequisites:** Android Studio (or the Android SDK command-line tools) and JDK 8+.

```bash
# Debug APK
./gradlew assembleDebug

# Release APK (requires a signing keystore)
./gradlew assembleRelease
```

The generated APK is located at `app/build/outputs/apk/`.

## Project structure

```
app/src/main/
├── java/com/tariq/whatsappstickers/
│   ├── MainActivity.java          # Pack list + "Add to WhatsApp" flow
│   ├── CreatePackActivity.java    # Image picker + pack creation
│   ├── model/
│   │   ├── StickerPack.java
│   │   └── Sticker.java
│   ├── provider/
│   │   └── StickerContentProvider.java   # WhatsApp sticker API
│   └── util/
│       ├── ImageUtils.java        # Resize & WebP conversion
│       └── StickerPackManager.java # Internal-storage pack management
└── res/
    ├── layout/  – activity_main, activity_create_pack, item_sticker_pack
    └── values/  – strings, colors, styles, plurals
```
