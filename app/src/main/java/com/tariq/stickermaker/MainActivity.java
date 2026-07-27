package com.tariq.stickermaker;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.GridLayoutManager;

import com.tariq.stickermaker.databinding.ActivityMainBinding;

import java.util.ArrayList;
import java.util.List;

/**
 * Entry point of the app. Shows a grid of images from device storage and lets
 * the user select multiple images to turn into a WhatsApp sticker pack.
 */
public class MainActivity extends AppCompatActivity implements ImageAdapter.SelectionListener {

    private static final int REQUEST_PERMISSION = 100;
    private static final int MIN_STICKERS = 3;
    private static final int MAX_STICKERS = 30;

    private ActivityMainBinding binding;
    private ImageAdapter adapter;

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        binding = ActivityMainBinding.inflate(getLayoutInflater());
        setContentView(binding.getRoot());

        setSupportActionBar(binding.toolbar);

        adapter = new ImageAdapter(this, this);
        binding.recyclerView.setLayoutManager(new GridLayoutManager(this, 3));
        binding.recyclerView.setAdapter(adapter);

        binding.fabNext.setOnClickListener(v -> proceedToStickerPack());

        requestStoragePermission();
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        getMenuInflater().inflate(R.menu.menu_main, menu);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(@NonNull MenuItem item) {
        if (item.getItemId() == R.id.action_select_all) {
            adapter.selectAll();
            return true;
        }
        if (item.getItemId() == R.id.action_deselect_all) {
            adapter.deselectAll();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    // -------------------------------------------------------------------------
    // Permission handling
    // -------------------------------------------------------------------------

    private void requestStoragePermission() {
        String permission = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                ? Manifest.permission.READ_MEDIA_IMAGES
                : Manifest.permission.READ_EXTERNAL_STORAGE;

        if (ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED) {
            loadImages();
        } else {
            ActivityCompat.requestPermissions(this, new String[]{permission}, REQUEST_PERMISSION);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_PERMISSION) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                loadImages();
            } else {
                Toast.makeText(this, R.string.permission_denied, Toast.LENGTH_LONG).show();
                binding.emptyView.setVisibility(View.VISIBLE);
            }
        }
    }

    // -------------------------------------------------------------------------
    // Load images from MediaStore
    // -------------------------------------------------------------------------

    private void loadImages() {
        List<Uri> images = new ArrayList<>();
        Uri collection = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;

        String[] projection = {MediaStore.Images.Media._ID};
        String sortOrder = MediaStore.Images.Media.DATE_ADDED + " DESC";

        try (Cursor cursor = getContentResolver().query(
                collection, projection, null, null, sortOrder)) {
            if (cursor != null) {
                int idColumn = cursor.getColumnIndexOrThrow(MediaStore.Images.Media._ID);
                while (cursor.moveToNext()) {
                    long id = cursor.getLong(idColumn);
                    Uri imageUri = Uri.withAppendedPath(collection, String.valueOf(id));
                    images.add(imageUri);
                }
            }
        }

        if (images.isEmpty()) {
            binding.emptyView.setVisibility(View.VISIBLE);
            binding.recyclerView.setVisibility(View.GONE);
        } else {
            binding.emptyView.setVisibility(View.GONE);
            binding.recyclerView.setVisibility(View.VISIBLE);
            adapter.setImages(images);
        }
    }

    // -------------------------------------------------------------------------
    // SelectionListener callbacks
    // -------------------------------------------------------------------------

    @Override
    public void onSelectionChanged(int selectedCount) {
        if (selectedCount == 0) {
            binding.selectionInfo.setVisibility(View.GONE);
            binding.fabNext.hide();
        } else {
            String label = getString(R.string.selection_count, selectedCount, MAX_STICKERS);
            binding.selectionInfo.setText(label);
            binding.selectionInfo.setVisibility(View.VISIBLE);
            binding.fabNext.show();
        }
    }

    // -------------------------------------------------------------------------
    // Proceed to sticker pack screen
    // -------------------------------------------------------------------------

    private void proceedToStickerPack() {
        List<Uri> selected = adapter.getSelectedImages();
        if (selected.size() < MIN_STICKERS) {
            Toast.makeText(this,
                    getString(R.string.min_stickers_required, MIN_STICKERS),
                    Toast.LENGTH_SHORT).show();
            return;
        }
        if (selected.size() > MAX_STICKERS) {
            Toast.makeText(this,
                    getString(R.string.max_stickers_exceeded, MAX_STICKERS),
                    Toast.LENGTH_SHORT).show();
            return;
        }

        ArrayList<String> uriStrings = new ArrayList<>();
        for (Uri uri : selected) {
            uriStrings.add(uri.toString());
        }

        Intent intent = new Intent(this, StickerPackActivity.class);
        intent.putStringArrayListExtra(StickerPackActivity.EXTRA_IMAGE_URIS, uriStrings);
        startActivity(intent);
    }
}
