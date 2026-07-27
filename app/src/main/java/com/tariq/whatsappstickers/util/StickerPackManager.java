package com.tariq.whatsappstickers.util;

import android.content.Context;
import android.net.Uri;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.tariq.whatsappstickers.model.Sticker;
import com.tariq.whatsappstickers.model.StickerPack;

import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/**
 * Manages sticker packs stored in the app's internal storage.
 *
 * <p>Directory layout inside {@code context.getFilesDir()}:
 * <pre>
 *   sticker_packs/
 *     &lt;packId&gt;/
 *       meta.json          – JSON with StickerPack metadata
 *       tray.webp          – 96×96 WebP tray icon
 *       sticker_01.webp    – 512×512 sticker
 *       sticker_02.webp
 *       …
 * </pre>
 */
public final class StickerPackManager {

    /** Sub-directory name inside filesDir used to store all packs. */
    private static final String PACKS_DIR = "sticker_packs";

    /** File name for the pack metadata JSON. */
    private static final String META_FILE = "meta.json";

    /** File name for the tray icon. */
    public static final String TRAY_FILE = "tray.webp";

    /** Minimum stickers required by WhatsApp. */
    public static final int MIN_STICKERS = 3;

    /** Maximum stickers allowed by WhatsApp. */
    public static final int MAX_STICKERS = 30;

    private static final Gson GSON = new Gson();

    private StickerPackManager() {}

    // -------------------------------------------------------------------------
    // Pack directory helpers
    // -------------------------------------------------------------------------

    /** Returns the root directory that contains all pack sub-directories. */
    public static File getPacksRootDir(Context context) {
        return new File(context.getFilesDir(), PACKS_DIR);
    }

    /** Returns the directory for a specific pack (does not guarantee it exists). */
    public static File getPackDir(Context context, String identifier) {
        return new File(getPacksRootDir(context), identifier);
    }

    /** Returns the tray icon file for a specific pack. */
    public static File getTrayFile(Context context, String identifier) {
        return new File(getPackDir(context, identifier), TRAY_FILE);
    }

    /**
     * Returns the sticker file for {@code fileName} inside the given pack directory.
     * Used by {@link com.tariq.whatsappstickers.provider.StickerContentProvider}.
     */
    public static File getStickerFile(Context context, String identifier, String fileName) {
        return new File(getPackDir(context, identifier), fileName);
    }

    // -------------------------------------------------------------------------
    // Load
    // -------------------------------------------------------------------------

    /**
     * Loads all sticker packs from internal storage and returns them.
     * Returns an empty list if none exist or an error occurs.
     */
    public static List<StickerPack> loadStickerPacks(Context context) {
        File root = getPacksRootDir(context);
        if (!root.exists()) {
            return Collections.emptyList();
        }
        File[] packDirs = root.listFiles(File::isDirectory);
        if (packDirs == null || packDirs.length == 0) {
            return Collections.emptyList();
        }

        List<StickerPack> packs = new ArrayList<>();
        for (File packDir : packDirs) {
            StickerPack pack = loadPackFromDir(packDir);
            if (pack != null) {
                packs.add(pack);
            }
        }
        return packs;
    }

    /** Loads a single sticker pack from its directory, or returns null on failure. */
    public static StickerPack loadPackFromDir(File packDir) {
        File metaFile = new File(packDir, META_FILE);
        if (!metaFile.exists()) {
            return null;
        }
        try (FileReader reader = new FileReader(metaFile)) {
            PackMeta meta = GSON.fromJson(reader, PackMeta.class);
            StickerPack pack = new StickerPack(
                    meta.identifier, meta.name, meta.publisher,
                    meta.trayImageFile, meta.publisherEmail,
                    meta.publisherWebsite, meta.privacyPolicyWebsite,
                    meta.licenseAgreementWebsite,
                    meta.imageDataVersion, meta.avoidCache);
            pack.androidPlayStoreLink = meta.androidPlayStoreLink;
            pack.iosAppStoreLink      = meta.iosAppStoreLink;

            List<Sticker> stickers = new ArrayList<>();
            if (meta.stickers != null) {
                for (StickerMeta sm : meta.stickers) {
                    Sticker s = new Sticker(sm.imageFileName,
                            sm.emojis != null ? sm.emojis : Collections.emptyList());
                    File sFile = new File(packDir, sm.imageFileName);
                    s.size = sFile.exists() ? sFile.length() : 0;
                    stickers.add(s);
                }
            }
            pack.setStickers(stickers);
            return pack;
        } catch (Exception e) {
            return null;
        }
    }

    // -------------------------------------------------------------------------
    // Create / Save
    // -------------------------------------------------------------------------

    /**
     * Creates a new sticker pack from the supplied image URIs.
     *
     * <ol>
     *   <li>Generates a unique pack identifier.</li>
     *   <li>Creates an internal directory for the pack.</li>
     *   <li>Converts each image to a 512×512 WebP sticker.</li>
     *   <li>Generates a 96×96 WebP tray icon from the first image.</li>
     *   <li>Persists pack metadata as JSON.</li>
     * </ol>
     *
     * @param context  application context
     * @param packName display name for the pack
     * @param imageUris URIs of the source images (3–30)
     * @return the created {@link StickerPack}
     * @throws IOException              if image conversion fails
     * @throws IllegalArgumentException if imageUris count is outside [3, 30]
     */
    public static StickerPack createPack(Context context, String packName, List<Uri> imageUris)
            throws IOException {
        if (imageUris.size() < MIN_STICKERS || imageUris.size() > MAX_STICKERS) {
            throw new IllegalArgumentException(
                    "A sticker pack must contain " + MIN_STICKERS + "–" + MAX_STICKERS + " stickers.");
        }

        String identifier = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        File packDir = getPackDir(context, identifier);
        if (!packDir.mkdirs()) {
            throw new IOException("Failed to create pack directory: " + packDir);
        }

        // Convert sticker images
        List<StickerMeta> stickerMetas = new ArrayList<>();
        for (int i = 0; i < imageUris.size(); i++) {
            String fileName = String.format("sticker_%02d.webp", i + 1);
            File dest = new File(packDir, fileName);
            ImageUtils.convertToWebP(context, imageUris.get(i), dest, ImageUtils.STICKER_SIZE_PX);
            stickerMetas.add(new StickerMeta(fileName,
                    Collections.singletonList("\uD83D\uDE00"))); // default emoji
        }

        // Create tray icon from the first sticker image
        File trayDest = new File(packDir, TRAY_FILE);
        ImageUtils.convertToWebP(context, imageUris.get(0), trayDest, ImageUtils.TRAY_SIZE_PX);

        // Save metadata JSON
        PackMeta meta = new PackMeta();
        meta.identifier              = identifier;
        meta.name                    = packName;
        meta.publisher               = "Tariq";
        meta.trayImageFile           = TRAY_FILE;
        meta.publisherEmail          = "";
        meta.publisherWebsite        = "";
        meta.privacyPolicyWebsite    = "";
        meta.licenseAgreementWebsite = "";
        meta.imageDataVersion        = "1";
        meta.avoidCache              = false;
        meta.stickers                = stickerMetas;
        savePackMeta(packDir, meta);

        // Build and return the StickerPack object
        StickerPack pack = new StickerPack(
                identifier, packName, meta.publisher,
                TRAY_FILE, meta.publisherEmail,
                meta.publisherWebsite, meta.privacyPolicyWebsite,
                meta.licenseAgreementWebsite,
                meta.imageDataVersion, false);

        List<Sticker> stickers = new ArrayList<>();
        for (StickerMeta sm : stickerMetas) {
            stickers.add(new Sticker(sm.imageFileName, sm.emojis));
        }
        pack.setStickers(stickers);
        return pack;
    }

    /**
     * Deletes a sticker pack and all its files from internal storage.
     *
     * @param context    application context
     * @param identifier pack identifier to delete
     */
    public static void deletePack(Context context, String identifier) {
        File packDir = getPackDir(context, identifier);
        deleteRecursive(packDir);
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private static void savePackMeta(File packDir, PackMeta meta) throws IOException {
        File metaFile = new File(packDir, META_FILE);
        try (FileWriter writer = new FileWriter(metaFile)) {
            GSON.toJson(meta, writer);
        }
    }

    private static void deleteRecursive(File file) {
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteRecursive(child);
                }
            }
        }
        if (!file.delete()) {
            // Log silently; best-effort deletion avoids throwing on partial failure
            android.util.Log.w("StickerPackManager", "Could not delete: " + file.getAbsolutePath());
        }
    }

    // -------------------------------------------------------------------------
    // JSON-serializable inner classes (no getters needed by Gson)
    // -------------------------------------------------------------------------

    /** Serialized representation of a sticker pack stored in meta.json. */
    private static class PackMeta {
        String identifier;
        String name;
        String publisher;
        String trayImageFile;
        String publisherEmail;
        String publisherWebsite;
        String privacyPolicyWebsite;
        String licenseAgreementWebsite;
        String androidPlayStoreLink;
        String iosAppStoreLink;
        String imageDataVersion;
        boolean avoidCache;
        List<StickerMeta> stickers;
    }

    /** Serialized representation of a single sticker entry in meta.json. */
    private static class StickerMeta {
        String imageFileName;
        List<String> emojis;

        StickerMeta(String imageFileName, List<String> emojis) {
            this.imageFileName = imageFileName;
            this.emojis        = emojis;
        }
    }
}
