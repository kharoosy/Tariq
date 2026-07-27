package com.tariq.whatsappstickers.model;

import java.util.List;

/**
 * Represents a sticker pack that can be added to WhatsApp.
 * Each pack must have 3–30 stickers, a tray icon, and unique identifier.
 */
public class StickerPack {

    /** Unique identifier for the sticker pack (e.g. UUID or slug). */
    public final String identifier;

    /** Display name shown in WhatsApp. */
    public final String name;

    /** Publisher name shown in WhatsApp. */
    public final String publisher;

    /** File name of the tray icon (96×96 WebP) stored in internal storage. */
    public final String trayImageFile;

    public final String publisherEmail;
    public final String publisherWebsite;
    public final String privacyPolicyWebsite;
    public final String licenseAgreementWebsite;

    /** Optional Play Store link shown in WhatsApp. */
    public String androidPlayStoreLink;

    /** Optional App Store link shown in WhatsApp. */
    public String iosAppStoreLink;

    /**
     * Version string for the sticker image data.
     * Increment this when any sticker image changes so WhatsApp refreshes its cache.
     */
    public String imageDataVersion;

    /**
     * When true, WhatsApp will not cache images from this provider.
     * Keep false for better performance; set to true only during development.
     */
    public boolean avoidCache;

    /** True when the user has already added this pack to WhatsApp. */
    public boolean isWhatsAppPackAdded;

    private List<Sticker> stickers;

    public StickerPack(String identifier, String name, String publisher,
                       String trayImageFile, String publisherEmail,
                       String publisherWebsite, String privacyPolicyWebsite,
                       String licenseAgreementWebsite,
                       String imageDataVersion, boolean avoidCache) {
        this.identifier   = identifier;
        this.name         = name;
        this.publisher    = publisher;
        this.trayImageFile = trayImageFile;
        this.publisherEmail         = publisherEmail;
        this.publisherWebsite       = publisherWebsite;
        this.privacyPolicyWebsite   = privacyPolicyWebsite;
        this.licenseAgreementWebsite = licenseAgreementWebsite;
        this.imageDataVersion = imageDataVersion;
        this.avoidCache       = avoidCache;
    }

    public List<Sticker> getStickers() {
        return stickers;
    }

    public void setStickers(List<Sticker> stickers) {
        this.stickers = stickers;
    }
}
