package com.tariq.stickermaker;

import android.app.ProgressDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.View;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.tariq.stickermaker.databinding.ActivityStickerPackBinding;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Lets the user name the sticker pack, preview the selected images, then
 * converts and sends the pack to WhatsApp.
 */
public class StickerPackActivity extends AppCompatActivity {

    public static final String EXTRA_IMAGE_URIS = "extra_image_uris";

    // WhatsApp intent action / extras
    private static final String ACTION_ADD_PACK =
            "com.whatsapp.intent.action.ENABLE_STICKER_PACK";
    private static final String EXTRA_STICKER_PACK_ID   = "sticker_pack_id";
    private static final String EXTRA_STICKER_PACK_AUTHORITY = "sticker_pack_authority";
    private static final String EXTRA_STICKER_PACK_NAME = "sticker_pack_name";

    private static final String AUTHORITY =
            "com.tariq.stickermaker.stickercontentprovider";

    private ActivityStickerPackBinding binding;
    private List<String> imageUriStrings;
    private PreviewAdapter previewAdapter;

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        binding = ActivityStickerPackBinding.inflate(getLayoutInflater());
        setContentView(binding.getRoot());

        if (getSupportActionBar() != null) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(true);
            getSupportActionBar().setTitle(R.string.create_pack_title);
        }

        imageUriStrings = getIntent().getStringArrayListExtra(EXTRA_IMAGE_URIS);
        if (imageUriStrings == null || imageUriStrings.isEmpty()) {
            finish();
            return;
        }

        // Show preview
        List<Uri> uris = new ArrayList<>();
        for (String s : imageUriStrings) uris.add(Uri.parse(s));

        previewAdapter = new PreviewAdapter(this, uris);
        binding.previewRecycler.setAdapter(previewAdapter);

        binding.btnAddToWhatsApp.setOnClickListener(v -> validateAndConvert());

        binding.imageCount.setText(getString(R.string.image_count_label, uris.size()));
    }

    @Override
    public boolean onSupportNavigateUp() {
        finish();
        return true;
    }

    // -------------------------------------------------------------------------
    // Validate name then kick off conversion
    // -------------------------------------------------------------------------

    private void validateAndConvert() {
        String packName = binding.editPackName.getText() != null
                ? binding.editPackName.getText().toString().trim()
                : "";
        if (TextUtils.isEmpty(packName)) {
            binding.editPackName.setError(getString(R.string.pack_name_required));
            return;
        }
        String authorName = binding.editAuthorName.getText() != null
                ? binding.editAuthorName.getText().toString().trim()
                : "";
        if (TextUtils.isEmpty(authorName)) {
            binding.editAuthorName.setError(getString(R.string.author_name_required));
            return;
        }

        String packId = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
        new ConvertTask(packId, packName, authorName).execute();
    }

    // -------------------------------------------------------------------------
    // AsyncTask: convert images → WebP stickers → register pack → send intent
    // -------------------------------------------------------------------------

    @SuppressWarnings("deprecation")
    private class ConvertTask extends AsyncTask<Void, Integer, String> {

        private final String packId;
        private final String packName;
        private final String authorName;
        private ProgressDialog dialog;

        ConvertTask(String packId, String packName, String authorName) {
            this.packId    = packId;
            this.packName  = packName;
            this.authorName = authorName;
        }

        @Override
        protected void onPreExecute() {
            dialog = new ProgressDialog(StickerPackActivity.this);
            dialog.setMessage(getString(R.string.converting));
            dialog.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
            dialog.setMax(imageUriStrings.size());
            dialog.setCancelable(false);
            dialog.show();
        }

        @Override
        protected String doInBackground(Void... voids) {
            try {
                List<Uri> uris = new ArrayList<>();
                for (String s : imageUriStrings) uris.add(Uri.parse(s));

                StickerPackManager manager = new StickerPackManager(StickerPackActivity.this);
                manager.createPack(packId, packName, authorName, uris,
                        progress -> publishProgress(progress));

                return null; // success
            } catch (Exception e) {
                return e.getMessage();
            }
        }

        @Override
        protected void onProgressUpdate(Integer... values) {
            if (dialog.isShowing()) dialog.setProgress(values[0]);
        }

        @Override
        protected void onPostExecute(String error) {
            if (dialog.isShowing()) dialog.dismiss();
            if (error != null) {
                Toast.makeText(StickerPackActivity.this,
                        getString(R.string.conversion_error, error),
                        Toast.LENGTH_LONG).show();
                return;
            }
            sendToWhatsApp();
        }
    }

    // -------------------------------------------------------------------------
    // Fire the WhatsApp "add sticker pack" intent
    // -------------------------------------------------------------------------

    private void sendToWhatsApp() {
        String packId = StickerPackManager.getLastCreatedPackId(this);
        String packName = StickerPackManager.getLastCreatedPackName(this);

        Intent intent = new Intent(ACTION_ADD_PACK);
        intent.putExtra(EXTRA_STICKER_PACK_ID,        packId);
        intent.putExtra(EXTRA_STICKER_PACK_AUTHORITY, AUTHORITY);
        intent.putExtra(EXTRA_STICKER_PACK_NAME,      packName);

        if (getPackageManager().resolveActivity(intent, 0) != null) {
            startActivityForResult(intent, 200);
        } else {
            Toast.makeText(this, R.string.whatsapp_not_installed, Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == 200) {
            if (resultCode == RESULT_CANCELED && data != null) {
                String error = data.getStringExtra("validation_error");
                if (!TextUtils.isEmpty(error)) {
                    Toast.makeText(this,
                            getString(R.string.whatsapp_error, error),
                            Toast.LENGTH_LONG).show();
                    return;
                }
            }
            if (resultCode == RESULT_OK) {
                Toast.makeText(this, R.string.pack_added_success, Toast.LENGTH_SHORT).show();
                finish();
            }
        }
    }
}
