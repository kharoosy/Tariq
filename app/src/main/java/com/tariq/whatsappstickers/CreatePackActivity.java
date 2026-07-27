package com.tariq.whatsappstickers;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.tariq.whatsappstickers.model.StickerPack;
import com.tariq.whatsappstickers.util.StickerPackManager;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Lets the user pick 3–30 images from device storage and create a new sticker pack.
 *
 * <p>Image picking uses the system document/media picker via
 * {@link Intent#ACTION_GET_CONTENT} with {@code EXTRA_ALLOW_MULTIPLE}, so no
 * storage permission is required on Android 11+ (API 30+). On older versions the
 * app requests READ_EXTERNAL_STORAGE at runtime.
 */
public class CreatePackActivity extends AppCompatActivity {

    private static final int REQUEST_STORAGE_PERMISSION = 100;

    private final ExecutorService executor    = Executors.newSingleThreadExecutor();
    private final Handler         mainHandler = new Handler(Looper.getMainLooper());

    private EditText    etPackName;
    private TextView    tvSelectedCount;
    private Button      btnPickImages;
    private Button      btnCreatePack;
    private ProgressBar progressBar;

    private final List<Uri> selectedImages = new ArrayList<>();

    // ---- Activity Result launcher for the system image picker ----

    private final ActivityResultLauncher<Intent> imagePickerLauncher =
            registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), result -> {
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    selectedImages.clear();
                    Intent data = result.getData();

                    if (data.getClipData() != null) {
                        // Multiple images selected
                        int count = data.getClipData().getItemCount();
                        for (int i = 0; i < count; i++) {
                            selectedImages.add(data.getClipData().getItemAt(i).getUri());
                        }
                    } else if (data.getData() != null) {
                        // Single image selected
                        selectedImages.add(data.getData());
                    }

                    updateSelectedCount();
                }
            });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_create_pack);

        etPackName      = findViewById(R.id.et_pack_name);
        tvSelectedCount = findViewById(R.id.tv_selected_count);
        btnPickImages   = findViewById(R.id.btn_pick_images);
        btnCreatePack   = findViewById(R.id.btn_create_pack);
        progressBar     = findViewById(R.id.progress_bar);

        btnPickImages.setOnClickListener(v -> checkPermissionAndPickImages());
        btnCreatePack.setOnClickListener(v -> createPack());

        updateSelectedCount();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        executor.shutdown();
    }

    // -------------------------------------------------------------------------
    // Permission handling
    // -------------------------------------------------------------------------

    private void checkPermissionAndPickImages() {
        if (Build.VERSION.SDK_INT >= 33) {
            // Android 13+ (API 33): READ_MEDIA_IMAGES
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_IMAGES)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{Manifest.permission.READ_MEDIA_IMAGES},
                        REQUEST_STORAGE_PERMISSION);
                return;
            }
        } else if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            // Android 10 and below: READ_EXTERNAL_STORAGE
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{Manifest.permission.READ_EXTERNAL_STORAGE},
                        REQUEST_STORAGE_PERMISSION);
                return;
            }
        }
        // Android 11–12 (API 30–32): no permission needed for ACTION_GET_CONTENT
        openImagePicker();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_STORAGE_PERMISSION) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                openImagePicker();
            } else {
                Toast.makeText(this, R.string.permission_denied, Toast.LENGTH_SHORT).show();
            }
        }
    }

    // -------------------------------------------------------------------------
    // Image picker
    // -------------------------------------------------------------------------

    private void openImagePicker() {
        Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
        intent.setType("image/*");
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        imagePickerLauncher.launch(Intent.createChooser(intent,
                getString(R.string.select_images)));
    }

    private void updateSelectedCount() {
        int count = selectedImages.size();
        tvSelectedCount.setText(getString(R.string.selected_images_count, count));
        btnCreatePack.setEnabled(count >= StickerPackManager.MIN_STICKERS
                && count <= StickerPackManager.MAX_STICKERS);
    }

    // -------------------------------------------------------------------------
    // Create pack
    // -------------------------------------------------------------------------

    private void createPack() {
        String packName = etPackName.getText().toString().trim();
        if (packName.isEmpty()) {
            etPackName.setError(getString(R.string.error_pack_name_empty));
            etPackName.requestFocus();
            return;
        }
        if (selectedImages.size() < StickerPackManager.MIN_STICKERS) {
            Toast.makeText(this,
                    getString(R.string.error_not_enough_stickers, StickerPackManager.MIN_STICKERS),
                    Toast.LENGTH_SHORT).show();
            return;
        }
        if (selectedImages.size() > StickerPackManager.MAX_STICKERS) {
            Toast.makeText(this,
                    getString(R.string.error_too_many_stickers, StickerPackManager.MAX_STICKERS),
                    Toast.LENGTH_SHORT).show();
            return;
        }

        setUiEnabled(false);
        progressBar.setVisibility(View.VISIBLE);

        List<Uri> uriSnapshot = new ArrayList<>(selectedImages);
        String nameSnapshot   = packName;

        executor.execute(() -> {
            StickerPack pack = null;
            Exception   error = null;
            try {
                pack = StickerPackManager.createPack(this, nameSnapshot, uriSnapshot);
            } catch (IOException | IllegalArgumentException e) {
                error = e;
            }

            final StickerPack result     = pack;
            final Exception   finalError = error;
            mainHandler.post(() -> {
                progressBar.setVisibility(View.GONE);
                if (result != null) {
                    Toast.makeText(this, R.string.pack_created_success, Toast.LENGTH_SHORT).show();
                    finish();
                } else {
                    setUiEnabled(true);
                    String msg = (finalError != null)
                            ? getString(R.string.pack_creation_error, finalError.getMessage())
                            : getString(R.string.pack_creation_failed);
                    Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
                }
            });
        });
    }

    private void setUiEnabled(boolean enabled) {
        etPackName.setEnabled(enabled);
        btnPickImages.setEnabled(enabled);
        btnCreatePack.setEnabled(enabled);
    }
}

