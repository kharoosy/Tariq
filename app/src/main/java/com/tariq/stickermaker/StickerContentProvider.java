package com.tariq.stickermaker;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.UriMatcher;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.io.IOException;
import java.util.List;

/**
 * ContentProvider that WhatsApp queries to retrieve sticker pack data.
 *
 * URI scheme (authority = com.tariq.stickermaker.stickercontentprovider):
 *  /metadata              → list of all packs
 *  /stickers/{pack_id}    → stickers in a specific pack
 *  /stickers/{pack_id}/{sticker_file}  → raw sticker file
 *  /stickers_asset/{pack_id}/tray_image.webp  → tray icon file
 */
public class StickerContentProvider extends ContentProvider {

    private static final String TAG = "StickerContentProvider";

    static final String AUTHORITY =
            "com.tariq.stickermaker.stickercontentprovider";

    // URI matcher codes
    private static final int METADATA         = 1;
    private static final int STICKERS_IN_PACK = 2;
    private static final int STICKER_FILE     = 3;
    private static final int STICKER_ASSET    = 4;

    private static final UriMatcher MATCHER = new UriMatcher(UriMatcher.NO_MATCH);

    static {
        MATCHER.addURI(AUTHORITY, "metadata",                  METADATA);
        MATCHER.addURI(AUTHORITY, "stickers/*",                STICKERS_IN_PACK);
        MATCHER.addURI(AUTHORITY, "stickers/*/*",              STICKER_FILE);
        MATCHER.addURI(AUTHORITY, "stickers_asset/*/*",        STICKER_ASSET);
    }

    // Columns that WhatsApp expects for the metadata cursor
    private static final String[] METADATA_COLUMNS = {
            "sticker_pack_id",
            "sticker_pack_name",
            "sticker_pack_publisher",
            "sticker_pack_icon",
            "android_play_store_link",
            "ios_app_store_link",
            "publisher_website",
            "privacy_policy_website",
            "license_agreement_website",
            "image_data_version",
            "avoid_cache",
            "animated_sticker_pack"
    };

    // Columns for the stickers cursor
    private static final String[] STICKERS_COLUMNS = {
            "sticker_file_name",
            "sticker_emoji"
    };

    @Override
    public boolean onCreate() {
        return true;
    }

    @Nullable
    @Override
    public Cursor query(@NonNull Uri uri, @Nullable String[] projection,
                        @Nullable String selection, @Nullable String[] selectionArgs,
                        @Nullable String sortOrder) {
        int match = MATCHER.match(uri);
        switch (match) {
            case METADATA:
                return getMetadata();
            case STICKERS_IN_PACK:
                return getStickersForPack(uri.getLastPathSegment());
            default:
                return null;
        }
    }

    @Nullable
    @Override
    public ParcelFileDescriptor openFile(@NonNull Uri uri, @NonNull String mode)
            throws IOException {
        int match = MATCHER.match(uri);
        if (match == STICKER_FILE || match == STICKER_ASSET) {
            List<String> segs = uri.getPathSegments();
            // segs: [stickers | stickers_asset, packId, fileName]
            if (segs.size() < 3) throw new IOException("Bad URI: " + uri);
            String packId   = segs.get(1);
            String fileName = segs.get(2);

            File packDir = StickerPackManager.getPackDir(getContext(), packId);
            File file    = new File(packDir, fileName);
            if (!file.exists()) throw new IOException("Sticker not found: " + file);

            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
        }
        throw new IOException("Unknown URI: " + uri);
    }

    // -------------------------------------------------------------------------
    // Cursor builders
    // -------------------------------------------------------------------------

    private Cursor getMetadata() {
        MatrixCursor cursor = new MatrixCursor(METADATA_COLUMNS);
        List<File> packs = StickerPackManager.getAllPackDirs(getContext());
        for (File packDir : packs) {
            try {
                StickerPackManager.StickerPackJson json =
                        StickerPackManager.readPackJson(packDir);
                cursor.addRow(new Object[]{
                        json.identifier,
                        json.name,
                        json.publisher,
                        json.tray_image_file,
                        "",  // android_play_store_link
                        "",  // ios_app_store_link
                        json.publisher_website,
                        json.privacy_policy_website,
                        json.license_agreement_website,
                        json.image_data_version,
                        json.avoid_cache ? 1 : 0,
                        json.animated_sticker_pack ? 1 : 0
                });
            } catch (Exception e) {
                Log.e(TAG, "Error reading pack: " + packDir.getName(), e);
            }
        }
        return cursor;
    }

    private Cursor getStickersForPack(String packId) {
        MatrixCursor cursor = new MatrixCursor(STICKERS_COLUMNS);
        File packDir = StickerPackManager.getPackDir(getContext(), packId);
        try {
            StickerPackManager.StickerPackJson json =
                    StickerPackManager.readPackJson(packDir);
            for (StickerPackManager.StickerFile sf : json.stickers) {
                String emojis = sf.emojis != null && sf.emojis.length > 0
                        ? sf.emojis[0] : "";
                cursor.addRow(new Object[]{sf.image_file, emojis});
            }
        } catch (Exception e) {
            Log.e(TAG, "Error reading stickers for pack: " + packId, e);
        }
        return cursor;
    }

    // -------------------------------------------------------------------------
    // Unused abstract methods
    // -------------------------------------------------------------------------

    @Nullable
    @Override
    public String getType(@NonNull Uri uri) { return null; }

    @Nullable
    @Override
    public Uri insert(@NonNull Uri uri, @Nullable ContentValues values) { return null; }

    @Override
    public int delete(@NonNull Uri uri, @Nullable String selection,
                      @Nullable String[] selectionArgs) { return 0; }

    @Override
    public int update(@NonNull Uri uri, @Nullable ContentValues values,
                      @Nullable String selection, @Nullable String[] selectionArgs) { return 0; }
}
