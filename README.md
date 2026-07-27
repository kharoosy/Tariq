# Tariq – WhatsApp Sticker App

A WhatsApp sticker app for Android based on the [official WhatsApp Sticker sample](https://github.com/WhatsApp/stickers).

## ⬇️ Download APK

The latest APK is automatically built on every push to `main` and published as a **GitHub Release**.

👉 **[Download latest APK from Releases](../../releases/latest)**

Alternatively, you can download the APK from the latest [Actions workflow run](../../actions/workflows/build-apk.yml) as an artifact.

> **Note:** Enable *Install from unknown sources* on your Android device before installing.

---

## 🛠️ Build Locally

### Prerequisites
- Android Studio or JDK 17
- Android SDK (API 34)

### Steps

```bash
git clone https://github.com/kharoosy/Tariq.git
cd Tariq
./gradlew assembleDebug
```

The APK will be at `app/build/outputs/apk/debug/app-debug.apk`.

---

## 📦 App Details

| Property | Value |
|---|---|
| Application ID | `com.tariq.mystickers` |
| Min SDK | 21 (Android 5.0) |
| Target SDK | 34 (Android 14) |

---

## 📝 About

This app lets users add custom sticker packs to WhatsApp. Sticker images are stored in `app/src/main/assets/` as WebP files.

To add your own stickers, edit `app/src/main/assets/contents.json` and place your `.webp` sticker images in the matching numbered folder.
