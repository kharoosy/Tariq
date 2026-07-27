package com.tariq.whatsappstickers.provider;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.UriMatcher;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.text.TextUtils;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.tariq.whatsappstickers.BuildConfig;
import com.tariq.whatsappstickers.model.Sticker;
import com.tariq.whatsappstickers.model.StickerPack;
import com.tariq.whatsappstickers.util.StickerPackManager;

import java.io.File;
import java.io.FileNotFoundException;
import java.util.List;
import java.util.Objects;

/**
 * Content Provider that exposes sticker pack data to WhatsApp.
 *
 * <h3>Supported URIs</h3>
 * <ul>
 *   <li>{@code content://{authority}/metadata} – cursor with all pack metadata</li>
 *   <li>{@code content://{authority}/metadata/{identifier}} – cursor for one pack</li>
 *   <li>{@code content://{authority}/stickers/{identifier}} – cursor with sticker list</li>
 *   <li>{@code content://{authority}/stickers_asset/{identifier}/{fileName}} – sticker image</li>
 *   <li>{@code content://{authority}/tray/{identifier}} – tray icon image</li>
 * </ul>
 */
public class StickerContentProvider extends ContentProvider {

    // ---- Column names expected by WhatsApp ----

    public static final String STICKER_PACK_IDENTIFIER  = "sticker_pack_identifier";
    public static final String STICKER_PACK_NAME        = "sticker_pack_name";
    public static final String STICKER_PACK_PUBLISHER   = "sticker_pack_publisher";
    public static final String STICKER_PACK_ICON        = "sticker_pack_tray_image_file";
    public static final String ANDROID_STORE_LINK       = "android_play_store_link";
    public static final String IOS_STORE_LINK           = "ios_app_store_link";
    public static final String PUBLISHER_EMAIL          = "sticker_pack_publisher_email";
    public static final String PUBLISHER_WEBSITE        = "sticker_pack_publisher_website";
    public static final String PRIVACY_POLICY_WEBSITE   = "sticker_pack_privacy_policy_website";
    public static final String LICENSE_AGREEMENT_WEBSITE = "sticker_pack_license_agreement_website";
    public static final String IMAGE_DATA_VERSION       = "image_data_version";
    public static final String AVOID_CACHE              = "avoid_cache";

    public static final String STICKER_FILE_NAME        = "sticker_file_name";
    public static final String STICKER_EMOJI            = "sticker_emoji";

    // ---- Content provider authority (built from applicationId) ----

    public static final String AUTHORITY = BuildConfig.CONTENT_PROVIDER_AUTHORITY;

    // ---- URI codes ----

    private static final int CODE_METADATA         = 1;
    private static final int CODE_METADATA_SINGLE  = 2;
    private static final int CODE_STICKERS         = 3;
    private static final int CODE_STICKER_ASSET    = 4;
    private static final int CODE_TRAY_ICON        = 5;

    private static final UriMatcher URI_MATCHER = new UriMatcher(UriMatcher.NO_MATCH);

    static {
        URI_MATCHER.addURI(AUTHORITY, "metadata",       CODE_METADATA);
        URI_MATCHER.addURI(AUTHORITY, "metadata/*",     CODE_METADATA_SINGLE);
        URI_MATCHER.addURI(AUTHORITY, "stickers/*",     CODE_STICKERS);
        URI_MATCHER.addURI(AUTHORITY, "stickers_asset/*/*", CODE_STICKER_ASSET);
        URI_MATCHER.addURI(AUTHORITY, "tray/*",         CODE_TRAY_ICON);
    }

    // ---- Metadata cursor column order ----

    private static final String[] METADATA_COLUMNS = {
            STICKER_PACK_IDENTIFIER,
            STICKER_PACK_NAME,
            STICKER_PACK_PUBLISHER,
            STICKER_PACK_ICON,
            ANDROID_STORE_LINK,
            IOS_STORE_LINK,
            PUBLISHER_EMAIL,
            PUBLISHER_WEBSITE,
            PRIVACY_POLICY_WEBSITE,
            LICENSE_AGREEMENT_WEBSITE,
            IMAGE_DATA_VERSION,
            AVOID_CACHE
    };

    // ---- Sticker-list cursor column order ----

    private static final String[] STICKER_COLUMNS = {
            STICKER_FILE_NAME,
            STICKER_EMOJI
    };

    // =========================================================================
    // ContentProvider lifecycle
    // =========================================================================

    @Override
    public boolean onCreate() {
        return true;
    }

    // =========================================================================
    // query()
    // =========================================================================

    @Nullable
    @Override
    public Cursor query(@NonNull Uri uri, @Nullable String[] projection,
                        @Nullable String selection, @Nullable String[] selectionArgs,
                        @Nullable String sortOrder) {
        switch (URI_MATCHER.match(uri)) {
            case CODE_METADATA:
                return buildMetadataCursor(uri, null);
            case CODE_METADATA_SINGLE:
                return buildMetadataCursor(uri, uri.getLastPathSegment());
            case CODE_STICKERS:
                return buildStickersCursor(uri, uri.getLastPathSegment());
            default:
                throw new IllegalArgumentException("Unknown URI: " + uri);
        }
    }

    // =========================================================================
    // openFile() – delivers sticker/tray image bytes to WhatsApp
    // =========================================================================

    @Nullable
    @Override
    public ParcelFileDescriptor openFile(@NonNull Uri uri, @NonNull String mode)
            throws FileNotFoundException {
        int code = URI_MATCHER.match(uri);
        if (code == CODE_STICKER_ASSET || code == CODE_TRAY_ICON) {
            return openImageFile(uri);
        }
        throw new IllegalArgumentException("Unknown URI for file: " + uri);
    }

    // =========================================================================
    // Unsupported write operations
    // =========================================================================

    @Nullable
    @Override
    public String getType(@NonNull Uri uri) {
        return null;
    }

    @Nullable
    @Override
    public Uri insert(@NonNull Uri uri, @Nullable ContentValues values) {
        throw new UnsupportedOperationException("Insert is not supported.");
    }

    @Override
    public int delete(@NonNull Uri uri, @Nullable String selection,
                      @Nullable String[] selectionArgs) {
        throw new UnsupportedOperationException("Delete is not supported.");
    }

    @Override
    public int update(@NonNull Uri uri, @Nullable ContentValues values,
                      @Nullable String selection, @Nullable String[] selectionArgs) {
        throw new UnsupportedOperationException("Update is not supported.");
    }

    // =========================================================================
    // Private helpers
    // =========================================================================

    /**
     * Builds a cursor containing metadata for all packs (when {@code identifier} is null)
     * or for the single pack with the given identifier.
     */
    private Cursor buildMetadataCursor(Uri notifyUri, @Nullable String identifier) {
        List<StickerPack> packs =
                StickerPackManager.loadStickerPacks(Objects.requireNonNull(getContext()));

        MatrixCursor cursor = new MatrixCursor(METADATA_COLUMNS);
        for (StickerPack pack : packs) {
            if (identifier == null || identifier.equals(pack.identifier)) {
                cursor.addRow(new Object[]{
                        pack.identifier,
                        pack.name,
                        pack.publisher,
                        pack.trayImageFile,
                        TextUtils.isEmpty(pack.androidPlayStoreLink) ? "" : pack.androidPlayStoreLink,
                        TextUtils.isEmpty(pack.iosAppStoreLink)      ? "" : pack.iosAppStoreLink,
                        pack.publisherEmail,
                        pack.publisherWebsite,
                        pack.privacyPolicyWebsite,
                        pack.licenseAgreementWebsite,
                        pack.imageDataVersion,
                        pack.avoidCache ? 1 : 0
                });
            }
        }
        cursor.setNotificationUri(Objects.requireNonNull(getContext()).getContentResolver(), notifyUri);
        return cursor;
    }

    /**
     * Builds a cursor containing all stickers for the given pack identifier.
     * Each emoji list is joined with a comma so WhatsApp can parse multiple emoji.
     */
    private Cursor buildStickersCursor(Uri notifyUri, String identifier) {
        List<StickerPack> packs =
                StickerPackManager.loadStickerPacks(Objects.requireNonNull(getContext()));

        MatrixCursor cursor = new MatrixCursor(STICKER_COLUMNS);
        for (StickerPack pack : packs) {
            if (identifier.equals(pack.identifier)) {
                List<Sticker> stickers = pack.getStickers();
                if (stickers != null) {
                    for (Sticker sticker : stickers) {
                        cursor.addRow(new Object[]{
                                sticker.imageFileName,
                                TextUtils.join(",", sticker.emojis)
                        });
                    }
                }
                break;
            }
        }
        cursor.setNotificationUri(Objects.requireNonNull(getContext()).getContentResolver(), notifyUri);
        return cursor;
    }

    /**
     * Opens the image file referred to by the URI and returns a read-only
     * {@link ParcelFileDescriptor}.
     *
     * <p>URI path segments:
     * <ul>
     *   <li>{@code stickers_asset/{identifier}/{fileName}} → two trailing segments</li>
     *   <li>{@code tray/{identifier}} → one trailing segment (tray icon)</li>
     * </ul>
     */
    private ParcelFileDescriptor openImageFile(Uri uri) throws FileNotFoundException {
        List<String> segments = uri.getPathSegments();
        if (segments.size() < 2) {
            throw new FileNotFoundException("Invalid URI: " + uri);
        }
        String identifier = segments.get(segments.size() - 2);
        String fileName   = segments.get(segments.size() - 1);

        // For the tray URI the last segment IS the identifier and the file is always tray.webp
        if (URI_MATCHER.match(uri) == CODE_TRAY_ICON) {
            identifier = fileName;   // last segment is the pack id
            fileName   = StickerPackManager.TRAY_FILE;
        }

        File imageFile = StickerPackManager.getStickerFile(
                Objects.requireNonNull(getContext()), identifier, fileName);
        if (!imageFile.exists()) {
            throw new FileNotFoundException("Sticker file not found: " + imageFile);
        }
        return ParcelFileDescriptor.open(imageFile, ParcelFileDescriptor.MODE_READ_ONLY);
    }
}
