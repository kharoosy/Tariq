# Tariq – WhatsApp Sticker Maker

An Android app .apk file that lets you pick images from your device gallery in bulk and add them as a custom sticker pack directly to WhatsApp.

---

## Features

| Feature | Detail |
|---|---|
| **Gallery browser** | Scrollable grid of every image on the device |
| **Batch selection** | Tap any image to toggle; toolbar "Select all / Deselect all" |
| **Min / Max guard** | WhatsApp requires 3–30 stickers per pack |
| **Auto-conversion** | Selected images are scaled to 512 × 512 WebP (≤ 100 KB each) and a 96 × 96 tray icon is generated automatically |
| **One-tap import** | Fires WhatsApp's `ENABLE_STICKER_PACK` intent so the pack lands in WhatsApp with a single tap |

---

## How to use

1. Open the app → grant storage permission.
2. Tap the images you want as stickers (3–30).
3. Tap **Create Pack**, enter a pack name and your name.
4. Tap **Add to WhatsApp** – WhatsApp opens and asks you to add the pack.

---

## Project structure

```
app/src/main/java/com/tariq/stickermaker/
  MainActivity.java          – gallery grid + batch selection
  ImageAdapter.java          – RecyclerView adapter with selection state
  StickerPackActivity.java   – pack naming + conversion progress + WhatsApp intent
  PreviewAdapter.java        – horizontal preview strip
  StickerPackManager.java    – image → WebP conversion, pack directory management
  StickerContentProvider.java – ContentProvider queried by WhatsApp
```

---

## WhatsApp sticker rules enforced

- **Format**: WebP
- **Sticker size**: exactly 512 × 512 px
- **File size**: ≤ 100 KB per sticker
- **Tray icon**: 96 × 96 px, ≤ 50 KB
- **Pack size**: 3–30 stickers

---

## Build

```bash
./gradlew assembleDebug
```

Minimum SDK: 21 (Android 5.0)  
Target SDK: 34 (Android 14)
