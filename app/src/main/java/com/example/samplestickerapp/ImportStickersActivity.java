/*
 * Batch image picker + on-device sticker pack builder.
 *
 * Lets the user pick several images straight from their gallery/files app,
 * converts each to WhatsApp's required format (512x512 WEBP, <100KB, plus a
 * 96x96 PNG tray icon) entirely on-device, and writes them into this app's
 * internal storage where StickerContentProvider serves them from
 * (see StickerContentProvider.CUSTOM_PACKS_DIR_NAME).
 */
package com.example.samplestickerapp;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Build;
import android.os.Bundle;
import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;

public class ImportStickersActivity extends BaseActivity {

    private static final int MIN_STICKERS = 3;
    private static final int MAX_STICKERS = 30;
    private static final int STICKER_DIMENSION = 512;
    private static final int TRAY_DIMENSION = 96;
    private static final int STICKER_MAX_BYTES = 100 * 1024;
    private static final int TRAY_MAX_BYTES = 50 * 1024;

    private final List<Uri> selectedUris = new ArrayList<>();
    private EditText packNameInput;
    private TextView selectedCountText;
    private Button selectImagesButton;
    private Button createPackButton;
    private ProgressBar progressBar;
    private ThumbnailAdapter thumbnailAdapter;

    private final ActivityResultLauncher<String> pickImagesLauncher =
            registerForActivityResult(new ActivityResultContracts.GetMultipleContents(), uris -> {
                if (uris == null) {
                    return;
                }
                selectedUris.clear();
                if (uris.size() > MAX_STICKERS) {
                    Toast.makeText(this, "WhatsApp allows up to " + MAX_STICKERS + " stickers per pack - using the first " + MAX_STICKERS, Toast.LENGTH_LONG).show();
                    selectedUris.addAll(uris.subList(0, MAX_STICKERS));
                } else {
                    selectedUris.addAll(uris);
                }
                refreshUi();
            });

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_import_stickers);
        if (getSupportActionBar() != null) {
            getSupportActionBar().setTitle("Create sticker pack");
        }

        packNameInput = findViewById(R.id.pack_name_input);
        selectedCountText = findViewById(R.id.selected_count_text);
        selectImagesButton = findViewById(R.id.select_images_button);
        createPackButton = findViewById(R.id.create_pack_button);
        progressBar = findViewById(R.id.import_progress);

        RecyclerView grid = findViewById(R.id.selected_images_grid);
        grid.setLayoutManager(new GridLayoutManager(this, 4));
        thumbnailAdapter = new ThumbnailAdapter();
        grid.setAdapter(thumbnailAdapter);

        selectImagesButton.setOnClickListener(v -> pickImagesLauncher.launch("image/*"));
        createPackButton.setOnClickListener(v -> onCreatePackClicked());

        packNameInput.addTextChangedListener(new android.text.TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {}

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                updateCreateButtonEnabled();
            }

            @Override
            public void afterTextChanged(android.text.Editable s) {}
        });

        refreshUi();
    }

    private void refreshUi() {
        thumbnailAdapter.notifyDataSetChanged();
        if (selectedUris.isEmpty()) {
            selectedCountText.setText("No images selected yet");
        } else {
            selectedCountText.setText(selectedUris.size() + " image(s) selected (need " + MIN_STICKERS + "-" + MAX_STICKERS + ")");
        }
        updateCreateButtonEnabled();
    }

    private void updateCreateButtonEnabled() {
        boolean nameOk = !TextUtils.isEmpty(packNameInput.getText().toString().trim());
        boolean countOk = selectedUris.size() >= MIN_STICKERS && selectedUris.size() <= MAX_STICKERS;
        createPackButton.setEnabled(nameOk && countOk);
    }

    private void onCreatePackClicked() {
        String packName = packNameInput.getText().toString().trim();
        selectImagesButton.setEnabled(false);
        createPackButton.setEnabled(false);
        progressBar.setVisibility(View.VISIBLE);
        new BuildPackTask(this, packName, new ArrayList<>(selectedUris)).execute();
    }

    private void onPackBuildFinished(@Nullable String errorMessage) {
        progressBar.setVisibility(View.GONE);
        selectImagesButton.setEnabled(true);
        updateCreateButtonEnabled();
        if (errorMessage != null) {
            Toast.makeText(this, "Couldn't create pack: " + errorMessage, Toast.LENGTH_LONG).show();
            return;
        }
        Toast.makeText(this, "Sticker pack created", Toast.LENGTH_SHORT).show();
        getContentResolver().notifyChange(StickerContentProvider.AUTHORITY_URI, null);
        // Reload from EntryActivity so the freshly-created pack shows up immediately.
        Intent intent = new Intent(this, EntryActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
        finish();
    }

    /** Shows a small thumbnail grid of the currently selected images. */
    private class ThumbnailAdapter extends RecyclerView.Adapter<ThumbnailAdapter.ThumbHolder> {
        @NonNull
        @Override
        public ThumbHolder onCreateViewHolder(@NonNull android.view.ViewGroup parent, int viewType) {
            View v = getLayoutInflater().inflate(R.layout.import_thumbnail_item, parent, false);
            return new ThumbHolder(v);
        }

        @Override
        public void onBindViewHolder(@NonNull ThumbHolder holder, int position) {
            Uri uri = selectedUris.get(position);
            try (InputStream in = getContentResolver().openInputStream(uri)) {
                BitmapFactory.Options opts = new BitmapFactory.Options();
                opts.inSampleSize = 4;
                Bitmap bmp = BitmapFactory.decodeStream(in, null, opts);
                holder.imageView.setImageBitmap(bmp);
            } catch (Exception e) {
                holder.imageView.setImageBitmap(null);
            }
        }

        @Override
        public int getItemCount() {
            return selectedUris.size();
        }

        class ThumbHolder extends RecyclerView.ViewHolder {
            final ImageView imageView;

            ThumbHolder(@NonNull View itemView) {
                super(itemView);
                imageView = itemView.findViewById(R.id.thumbnail_image);
            }
        }
    }

    /** Converts the selected images to sticker-compliant files and writes contents.json. */
    private static class BuildPackTask extends AsyncTask<Void, Void, String> {
        private final WeakReference<ImportStickersActivity> activityRef;
        private final Context appContext;
        private final String packName;
        private final List<Uri> uris;

        BuildPackTask(ImportStickersActivity activity, String packName, List<Uri> uris) {
            this.activityRef = new WeakReference<>(activity);
            this.appContext = activity.getApplicationContext();
            this.packName = packName;
            this.uris = uris;
        }

        @Override
        protected String doInBackground(Void... voids) {
            try {
                String identifier = "custom_" + System.currentTimeMillis();
                File packDir = new File(StickerContentProvider.getCustomPacksDir(appContext), identifier);
                if (!packDir.mkdirs() && !packDir.isDirectory()) {
                    return "could not create storage folder";
                }

                JSONArray stickersJson = new JSONArray();
                Bitmap firstBitmapForTray = null;

                for (int i = 0; i < uris.size(); i++) {
                    Bitmap decoded = decodeBitmap(uris.get(i));
                    if (decoded == null) {
                        return "couldn't read one of the selected images";
                    }
                    if (i == 0) {
                        firstBitmapForTray = decoded;
                    }
                    Bitmap square = fitSquare(decoded, STICKER_DIMENSION);
                    String fileName = String.format("%02d.webp", i + 1);
                    File out = new File(packDir, fileName);
                    saveWebpUnderLimit(square, out, STICKER_MAX_BYTES);

                    JSONObject stickerObj = new JSONObject();
                    stickerObj.put("image_file", fileName);
                    JSONArray emojis = new JSONArray();
                    emojis.put("\uD83D\uDE00"); // 😀
                    stickerObj.put("emojis", emojis);
                    stickerObj.put("accessibility_text", packName + " sticker " + (i + 1));
                    stickersJson.put(stickerObj);
                }

                String trayFileName = "tray_" + identifier + ".png";
                Bitmap traySquare = fitSquare(firstBitmapForTray, TRAY_DIMENSION);
                File trayOut = new File(packDir, trayFileName);
                savePngUnderLimit(traySquare, trayOut, TRAY_MAX_BYTES);

                JSONObject packObj = new JSONObject();
                packObj.put("identifier", identifier);
                packObj.put("name", packName);
                packObj.put("publisher", "Me");
                packObj.put("tray_image_file", trayFileName);
                packObj.put("image_data_version", "1");
                packObj.put("avoid_cache", false);
                packObj.put("publisher_email", "");
                packObj.put("publisher_website", "");
                packObj.put("privacy_policy_website", "");
                packObj.put("license_agreement_website", "");
                packObj.put("stickers", stickersJson);

                File contentsFile = StickerContentProvider.getCustomContentsFile(appContext);
                JSONObject contents;
                if (contentsFile.exists()) {
                    contents = new JSONObject(readFile(contentsFile));
                } else {
                    contents = new JSONObject();
                    contents.put("android_play_store_link", "");
                    contents.put("ios_app_store_link", "");
                    contents.put("sticker_packs", new JSONArray());
                }
                contents.getJSONArray("sticker_packs").put(packObj);
                writeFile(contentsFile, contents.toString(2));

                return null; // success
            } catch (Exception e) {
                Log.e("ImportStickersActivity", "failed to build sticker pack", e);
                return e.getMessage() != null ? e.getMessage() : "unknown error";
            }
        }

        @Override
        protected void onPostExecute(String errorMessage) {
            ImportStickersActivity activity = activityRef.get();
            if (activity != null) {
                activity.onPackBuildFinished(errorMessage);
            }
        }

        @Nullable
        private Bitmap decodeBitmap(Uri uri) throws IOException {
            // First pass: read bounds only, to pick a safe sample size for large photos.
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            try (InputStream in = appContext.getContentResolver().openInputStream(uri)) {
                BitmapFactory.decodeStream(in, null, bounds);
            }
            int sample = 1;
            int targetMax = STICKER_DIMENSION * 2;
            while (bounds.outWidth / (sample * 2) >= targetMax || bounds.outHeight / (sample * 2) >= targetMax) {
                sample *= 2;
            }
            BitmapFactory.Options opts = new BitmapFactory.Options();
            opts.inSampleSize = sample;
            try (InputStream in = appContext.getContentResolver().openInputStream(uri)) {
                return BitmapFactory.decodeStream(in, null, opts);
            }
        }

        /** Pads (never crops) the bitmap onto a transparent square canvas of the given size. */
        private Bitmap fitSquare(Bitmap src, int size) {
            float scale = Math.min((float) size / src.getWidth(), (float) size / src.getHeight());
            int scaledW = Math.round(src.getWidth() * scale);
            int scaledH = Math.round(src.getHeight() * scale);
            Bitmap scaled = Bitmap.createScaledBitmap(src, Math.max(scaledW, 1), Math.max(scaledH, 1), true);

            Bitmap canvasBitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
            Canvas canvas = new Canvas(canvasBitmap);
            int left = (size - scaled.getWidth()) / 2;
            int top = (size - scaled.getHeight()) / 2;
            canvas.drawBitmap(scaled, left, top, null);
            return canvasBitmap;
        }

        private void saveWebpUnderLimit(Bitmap bmp, File out, int maxBytes) throws IOException {
            int[] qualities = {90, 80, 70, 60, 50, 40, 30, 20};
            for (int q : qualities) {
                try (FileOutputStream fos = new FileOutputStream(out)) {
                    Bitmap.CompressFormat format = Build.VERSION.SDK_INT >= 30
                            ? Bitmap.CompressFormat.WEBP_LOSSY
                            : Bitmap.CompressFormat.WEBP;
                    bmp.compress(format, q, fos);
                }
                if (out.length() <= maxBytes) {
                    return;
                }
            }
            // Best effort at lowest quality tried - leave as-is; the pack validator
            // will surface a clear error if it's still over the limit.
        }

        private void savePngUnderLimit(Bitmap bmp, File out, int maxBytes) throws IOException {
            Bitmap current = bmp;
            for (int attempt = 0; attempt < 6; attempt++) {
                try (FileOutputStream fos = new FileOutputStream(out)) {
                    current.compress(Bitmap.CompressFormat.PNG, 100, fos);
                }
                if (out.length() <= maxBytes) {
                    return;
                }
                int newW = (int) (current.getWidth() * 0.85);
                int newH = (int) (current.getHeight() * 0.85);
                if (newW < 24 || newH < 24) {
                    return;
                }
                current = Bitmap.createScaledBitmap(current, newW, newH, true);
            }
        }

        private String readFile(File file) throws IOException {
            StringBuilder sb = new StringBuilder();
            try (java.io.FileInputStream fis = new java.io.FileInputStream(file);
                 java.io.InputStreamReader reader = new java.io.InputStreamReader(fis, "UTF-8")) {
                char[] buf = new char[4096];
                int read;
                while ((read = reader.read(buf)) != -1) {
                    sb.append(buf, 0, read);
                }
            }
            return sb.toString();
        }

        private void writeFile(File file, String content) throws IOException {
            try (FileOutputStream fos = new FileOutputStream(file)) {
                fos.write(content.getBytes("UTF-8"));
            }
        }
    }
}
