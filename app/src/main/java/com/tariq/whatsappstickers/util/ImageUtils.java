package com.tariq.whatsappstickers.util;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Build;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Utility methods for image resizing and WebP conversion.
 *
 * <p>WhatsApp sticker requirements:
 * <ul>
 *   <li>Sticker images: exactly 512×512 pixels, WebP format, ≤ 100 KB.</li>
 *   <li>Tray icon: exactly 96×96 pixels, WebP format, ≤ 50 KB.</li>
 * </ul>
 */
public final class ImageUtils {

    public static final int STICKER_SIZE_PX = 512;
    public static final int TRAY_SIZE_PX    = 96;

    private ImageUtils() {}

    /**
     * Reads the image at {@code sourceUri}, scales it to {@code targetSize}×{@code targetSize},
     * encodes it as WebP, and writes the result to {@code destFile}.
     *
     * @param context    used to open the content URI
     * @param sourceUri  URI of the source image (content:// or file://)
     * @param destFile   destination file; parent directories must already exist
     * @param targetSize side length in pixels (512 for stickers, 96 for tray)
     * @throws IOException if reading or writing fails
     */
    public static void convertToWebP(Context context, Uri sourceUri, File destFile, int targetSize)
            throws IOException {
        Bitmap source;
        try (InputStream in = context.getContentResolver().openInputStream(sourceUri)) {
            if (in == null) {
                throw new IOException("Cannot open input stream for URI: " + sourceUri);
            }
            source = BitmapFactory.decodeStream(in);
        }
        if (source == null) {
            throw new IOException("Failed to decode image from URI: " + sourceUri);
        }

        Bitmap scaled = scaleBitmap(source, targetSize);
        source.recycle();

        writeBitmapAsWebP(scaled, destFile);
        scaled.recycle();
    }

    /**
     * Reads the image at {@code sourceFile}, scales it, and writes a WebP file.
     */
    public static void convertToWebP(File sourceFile, File destFile, int targetSize)
            throws IOException {
        Bitmap source = BitmapFactory.decodeFile(sourceFile.getAbsolutePath());
        if (source == null) {
            throw new IOException("Failed to decode image: " + sourceFile);
        }
        Bitmap scaled = scaleBitmap(source, targetSize);
        source.recycle();
        writeBitmapAsWebP(scaled, destFile);
        scaled.recycle();
    }

    /**
     * Scales {@code src} to a square of {@code size}×{@code size} pixels using high-quality
     * filtering. Letterboxes (transparent padding) if the aspect ratio differs.
     */
    private static Bitmap scaleBitmap(Bitmap src, int size) {
        Bitmap result = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(result);
        Paint paint   = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);

        // Compute a centered, aspect-ratio-preserving rect.
        float srcW = src.getWidth();
        float srcH = src.getHeight();
        float scale = Math.min(size / srcW, size / srcH);
        int drawW = Math.round(srcW * scale);
        int drawH = Math.round(srcH * scale);
        int left  = (size - drawW) / 2;
        int top   = (size - drawH) / 2;

        canvas.drawBitmap(src, null, new Rect(left, top, left + drawW, top + drawH), paint);
        return result;
    }

    /**
     * Compresses {@code bitmap} as WebP and writes it to {@code file}.
     * Uses lossless encoding on API 30+ and high-quality lossy on older versions.
     */
    @SuppressWarnings("deprecation")
    private static void writeBitmapAsWebP(Bitmap bitmap, File file) throws IOException {
        try (FileOutputStream out = new FileOutputStream(file)) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                bitmap.compress(Bitmap.CompressFormat.WEBP_LOSSLESS, 100, out);
            } else {
                // WEBP with quality 100 is effectively lossless on older APIs
                bitmap.compress(Bitmap.CompressFormat.WEBP, 100, out);
            }
        }
    }
}
