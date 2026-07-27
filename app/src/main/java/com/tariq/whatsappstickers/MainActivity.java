package com.tariq.whatsappstickers;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.google.android.material.floatingactionbutton.FloatingActionButton;
import com.tariq.whatsappstickers.model.StickerPack;
import com.tariq.whatsappstickers.provider.StickerContentProvider;
import com.tariq.whatsappstickers.util.StickerPackManager;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Main screen: lists all sticker packs and lets the user add them to WhatsApp
 * or delete them. A FAB opens {@link CreatePackActivity} to create a new pack.
 */
public class MainActivity extends AppCompatActivity {

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler         mainHandler = new Handler(Looper.getMainLooper());

    private RecyclerView recyclerView;
    private TextView     emptyView;
    private PackAdapter  adapter;

    /** Launcher for the "add sticker pack to WhatsApp" intent. */
    private final ActivityResultLauncher<Intent> addToWhatsAppLauncher =
            registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), result -> {
                if (result.getResultCode() == Activity.RESULT_CANCELED) {
                    Intent data = result.getData();
                    String error = (data != null) ? data.getStringExtra("validation_error") : null;
                    String msg = (error != null)
                            ? getString(R.string.add_pack_error, error)
                            : getString(R.string.add_pack_cancelled);
                    Toast.makeText(this, msg, Toast.LENGTH_LONG).show();
                } else if (result.getResultCode() == Activity.RESULT_OK) {
                    Toast.makeText(this, R.string.add_pack_success, Toast.LENGTH_SHORT).show();
                    loadPacks();
                }
            });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        recyclerView = findViewById(R.id.recycler_packs);
        emptyView    = findViewById(R.id.text_empty);

        adapter = new PackAdapter();
        recyclerView.setLayoutManager(new LinearLayoutManager(this));
        recyclerView.setAdapter(adapter);

        FloatingActionButton fab = findViewById(R.id.fab_create);
        fab.setOnClickListener(v ->
                startActivity(new Intent(this, CreatePackActivity.class)));
    }

    @Override
    protected void onResume() {
        super.onResume();
        loadPacks();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        executor.shutdown();
    }

    // -------------------------------------------------------------------------
    // Load sticker packs in background
    // -------------------------------------------------------------------------

    private void loadPacks() {
        executor.execute(() -> {
            List<StickerPack> packs = StickerPackManager.loadStickerPacks(this);
            mainHandler.post(() -> {
                adapter.setPacks(packs);
                emptyView.setVisibility(packs.isEmpty() ? View.VISIBLE : View.GONE);
                recyclerView.setVisibility(packs.isEmpty() ? View.GONE : View.VISIBLE);
            });
        });
    }

    // -------------------------------------------------------------------------
    // Add pack to WhatsApp
    // -------------------------------------------------------------------------

    /**
     * Fires the WhatsApp intent to add a sticker pack.
     * WhatsApp responds via the {@link #addToWhatsAppLauncher} callback.
     */
    private void addPackToWhatsApp(StickerPack pack) {
        Intent intent = new Intent();
        intent.setAction("com.whatsapp.intent.action.ENABLE_STICKER_PACK");
        intent.putExtra("sticker_pack_id",        pack.identifier);
        intent.putExtra("sticker_pack_authority", StickerContentProvider.AUTHORITY);
        intent.putExtra("sticker_pack_name",      pack.name);
        try {
            addToWhatsAppLauncher.launch(intent);
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this,
                    getString(R.string.whatsapp_not_installed), Toast.LENGTH_LONG).show();
        }
    }

    // -------------------------------------------------------------------------
    // Delete pack
    // -------------------------------------------------------------------------

    private void confirmDeletePack(StickerPack pack) {
        new AlertDialog.Builder(this)
                .setTitle(R.string.delete_pack_title)
                .setMessage(getString(R.string.delete_pack_message, pack.name))
                .setPositiveButton(R.string.delete, (dialog, which) -> deletePack(pack))
                .setNegativeButton(android.R.string.cancel, null)
                .show();
    }

    private void deletePack(StickerPack pack) {
        executor.execute(() -> {
            StickerPackManager.deletePack(this, pack.identifier);
            mainHandler.post(() -> {
                Toast.makeText(this, R.string.pack_deleted, Toast.LENGTH_SHORT).show();
                loadPacks();
            });
        });
    }

    // =========================================================================
    // RecyclerView adapter
    // =========================================================================

    private class PackAdapter extends RecyclerView.Adapter<PackAdapter.VH> {

        private List<StickerPack> packs = new ArrayList<>();

        void setPacks(List<StickerPack> packs) {
            this.packs = packs;
            notifyDataSetChanged();
        }

        @NonNull
        @Override
        public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext())
                    .inflate(R.layout.item_sticker_pack, parent, false);
            return new VH(v);
        }

        @Override
        public void onBindViewHolder(@NonNull VH holder, int position) {
            holder.bind(packs.get(position));
        }

        @Override
        public int getItemCount() { return packs.size(); }

        class VH extends RecyclerView.ViewHolder {
            final TextView textName;
            final TextView textCount;
            final Button   btnAdd;
            final Button   btnDelete;

            VH(@NonNull View v) {
                super(v);
                textName  = v.findViewById(R.id.text_pack_name);
                textCount = v.findViewById(R.id.text_sticker_count);
                btnAdd    = v.findViewById(R.id.btn_add_to_whatsapp);
                btnDelete = v.findViewById(R.id.btn_delete_pack);
            }

            void bind(StickerPack pack) {
                textName.setText(pack.name);
                int count = pack.getStickers() == null ? 0 : pack.getStickers().size();
                textCount.setText(getResources().getQuantityString(
                        R.plurals.sticker_count, count, count));

                btnAdd.setOnClickListener(v -> addPackToWhatsApp(pack));
                btnDelete.setOnClickListener(v -> confirmDeletePack(pack));
            }
        }
    }
}

