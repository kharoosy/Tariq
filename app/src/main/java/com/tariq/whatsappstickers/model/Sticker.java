package com.tariq.whatsappstickers.model;

import java.util.List;

/**
 * Represents a single sticker within a {@link StickerPack}.
 * The image file must be a 512×512 WebP stored in the pack's internal-storage directory.
 */
public class Sticker {

    /** File name of the sticker image (e.g. "sticker_01.webp"). */
    public final String imageFileName;

    /**
     * Up to three emoji associated with this sticker.
     * WhatsApp uses these for sticker search.
     */
    public final List<String> emojis;

    /** File size in bytes (populated when the pack is loaded). */
    public long size;

    public Sticker(String imageFileName, List<String> emojis) {
        this.imageFileName = imageFileName;
        this.emojis        = emojis;
    }
}
