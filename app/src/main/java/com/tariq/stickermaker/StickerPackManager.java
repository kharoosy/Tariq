package com.tariq.stickermaker;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

/**
 * Handles converting a list of image URIs into a WhatsApp-compatible sticker
 * pack stored in the app's private storage.
 *
 * Sticker rules enforced by WhatsApp:
 *  - Exactly 512 × 512 pixels
 *  - WebP format
 *  - File size ≤ 100 KB per sticker
 *  - 3–30 stickers per pack
 *  - Tray image: 96 × 96 WebP ≤ 50 KB (first sticker is reused as tray image)
 */
public class StickerPackManager {

    private static final int    STICKER_SIZE       = 512;
    private static final int    TRAY_SIZE          = 96;
    private static final int    MAX_KB             = 100 * 1024; // 100 KB in bytes
    private static final int    TRAY_MAX_KB        = 50  * 1024; // 50 KB
    private static final String DEFAULT_WEBSITE    = "https://tariq.app";
    private static final boolean ANIMATED_PACK     = false;

    // SharedPreferences keys to pass pack info to StickerPackActivity after creation
    private static final String PREFS       = "sticker_prefs";
    private static final String KEY_PACK_ID = "last_pack_id";
    private static final String KEY_PACK_NAME = "last_pack_name";

    public interface ProgressCallback {
        void onProgress(int done);
    }

    private final Context context;

    public StickerPackManager(Context context) {
        this.context = context.getApplicationContext();
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Creates a sticker pack directory, converts all images, writes the pack
     * metadata JSON, and persists the pack id/name for later retrieval.
     */
    public void createPack(String packId, String packName, String authorName,
                           List<Uri> imageUris, ProgressCallback callback)
            throws IOException {

        File packDir = getPackDir(packId);
        if (!packDir.exists() && !packDir.mkdirs()) {
            throw new IOException("Cannot create pack directory: " + packDir);
        }

        List<StickerFile> stickerFiles = new ArrayList<>();
        int done = 0;

        for (Uri uri : imageUris) {
            String fileName = "sticker_" + (done + 1) + ".webp";
            File outFile = new File(packDir, fileName);

            convertToWebp(uri, outFile, STICKER_SIZE, MAX_KB);
            stickerFiles.add(new StickerFile(fileName, new String[]{"😀"}));

            done++;
            if (callback != null) callback.onProgress(done);
        }

        // Use the first sticker as the tray icon (96 × 96)
        File trayFile = new File(packDir, "tray.webp");
        convertToWebp(imageUris.get(0), trayFile, TRAY_SIZE, TRAY_MAX_KB);

        // Write stickers.json
        StickerPackJson json = new StickerPackJson(
                packId, packName, authorName, "tray.webp",
                DEFAULT_WEBSITE, DEFAULT_WEBSITE,
                DEFAULT_WEBSITE, ANIMATED_PACK,
                stickerFiles);
        writeJson(packDir, json);

        // Persist for retrieval
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_PACK_ID,   packId)
                .putString(KEY_PACK_NAME, packName)
                .apply();
    }

    // -------------------------------------------------------------------------
    // Static helpers for ContentProvider and StickerPackActivity
    // -------------------------------------------------------------------------

    public static String getLastCreatedPackId(Context ctx) {
        return ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(KEY_PACK_ID, "");
    }

    public static String getLastCreatedPackName(Context ctx) {
        return ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(KEY_PACK_NAME, "");
    }

    /** Returns all pack directories under the stickers root. */
    public static List<File> getAllPackDirs(Context ctx) {
        List<File> packs = new ArrayList<>();
        File root = getStickersRoot(ctx);
        if (root.exists() && root.isDirectory()) {
            File[] dirs = root.listFiles(File::isDirectory);
            if (dirs != null) {
                for (File d : dirs) packs.add(d);
            }
        }
        return packs;
    }

    /** Parse the stickers.json of a given pack directory. */
    public static StickerPackJson readPackJson(File packDir) throws IOException {
        File jsonFile = new File(packDir, "stickers.json");
        StringBuilder sb = new StringBuilder();
        try (java.io.BufferedReader br = new java.io.BufferedReader(
                new java.io.FileReader(jsonFile))) {
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
        }
        return new Gson().fromJson(sb.toString(), StickerPackJson.class);
    }

    public static File getPackDir(Context ctx, String packId) {
        return new File(getStickersRoot(ctx), packId);
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private File getPackDir(String packId) {
        return new File(getStickersRoot(context), packId);
    }

    private static File getStickersRoot(Context ctx) {
        return new File(ctx.getFilesDir(), "sticker_packs");
    }

    /**
     * Reads a URI, decodes the bitmap, scales it to {@code targetSize}×{@code targetSize},
     * and encodes it as WebP with quality reduced until the file fits in {@code maxBytes}.
     */
    private void convertToWebp(Uri uri, File outFile, int targetSize, int maxBytes)
            throws IOException {

        Bitmap bitmap = decodeSampledBitmap(uri, targetSize);
        Bitmap scaled  = Bitmap.createScaledBitmap(bitmap, targetSize, targetSize, true);
        if (scaled != bitmap) bitmap.recycle();

        int quality = 90;
        byte[] webpBytes;

        do {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                scaled.compress(Bitmap.CompressFormat.WEBP_LOSSY, quality, baos);
            } else {
                //noinspection deprecation
                scaled.compress(Bitmap.CompressFormat.WEBP, quality, baos);
            }
            webpBytes = baos.toByteArray();
            quality -= 5;
        } while (webpBytes.length > maxBytes && quality > 10);

        scaled.recycle();

        try (FileOutputStream fos = new FileOutputStream(outFile)) {
            fos.write(webpBytes);
        }
    }

    /**
     * Decodes the image at {@code uri} using in-sample-size so the decoded
     * bitmap is not unnecessarily huge before scaling.
     */
    private Bitmap decodeSampledBitmap(Uri uri, int targetSize) throws IOException {
        try (InputStream is1 = context.getContentResolver().openInputStream(uri)) {
            if (is1 == null) throw new IOException("Cannot open: " + uri);
            BitmapFactory.Options opts = new BitmapFactory.Options();
            opts.inJustDecodeBounds = true;
            BitmapFactory.decodeStream(is1, null, opts);
            opts.inSampleSize    = calculateInSampleSize(opts, targetSize, targetSize);
            opts.inJustDecodeBounds = false;

            try (InputStream is2 = context.getContentResolver().openInputStream(uri)) {
                if (is2 == null) throw new IOException("Cannot open: " + uri);
                Bitmap bmp = BitmapFactory.decodeStream(is2, null, opts);
                if (bmp == null) throw new IOException("Failed to decode: " + uri);
                return bmp;
            }
        }
    }

    private static int calculateInSampleSize(BitmapFactory.Options options,
                                              int reqWidth, int reqHeight) {
        int height = options.outHeight;
        int width  = options.outWidth;
        int inSampleSize = 1;
        if (height > reqHeight || width > reqWidth) {
            int halfHeight = height / 2;
            int halfWidth  = width / 2;
            while ((halfHeight / inSampleSize) >= reqHeight
                    && (halfWidth / inSampleSize) >= reqWidth) {
                inSampleSize *= 2;
            }
        }
        return inSampleSize;
    }

    private void writeJson(File packDir, StickerPackJson json) throws IOException {
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        File jsonFile = new File(packDir, "stickers.json");
        try (PrintWriter pw = new PrintWriter(jsonFile)) {
            pw.print(gson.toJson(json));
        }
    }

    // -------------------------------------------------------------------------
    // JSON model classes (mirroring WhatsApp's sticker content provider schema)
    // -------------------------------------------------------------------------

    public static class StickerPackJson {
        public final String identifier;
        public final String name;
        public final String publisher;
        public final String tray_image_file;
        public final String publisher_website;
        public final String privacy_policy_website;
        public final String license_agreement_website;
        public final String image_data_version = "1";
        public final boolean avoid_cache = false;
        public final boolean animated_sticker_pack;
        public final List<StickerFile> stickers;

        public StickerPackJson(String id, String name, String publisher,
                               String tray, String website, String privacy,
                               String license, boolean animated,
                               List<StickerFile> stickers) {
            this.identifier                = id;
            this.name                      = name;
            this.publisher                 = publisher;
            this.tray_image_file           = tray;
            this.publisher_website         = website;
            this.privacy_policy_website    = privacy;
            this.license_agreement_website = license;
            this.animated_sticker_pack     = animated;
            this.stickers                  = stickers;
        }
    }

    public static class StickerFile {
        public final String image_file;
        public final String[] emojis;

        public StickerFile(String imageFile, String[] emojis) {
            this.image_file = imageFile;
            this.emojis     = emojis;
        }
    }
}
