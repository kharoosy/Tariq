package com.tariq.stickermaker;

import android.content.Context;
import android.net.Uri;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.bumptech.glide.Glide;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * RecyclerView adapter that displays a grid of device images and supports
 * multi-selection (tap to toggle, long-press to start selection).
 */
public class ImageAdapter extends RecyclerView.Adapter<ImageAdapter.ImageViewHolder> {

    public interface SelectionListener {
        void onSelectionChanged(int selectedCount);
    }

    private final Context context;
    private final SelectionListener listener;
    private final List<Uri> images = new ArrayList<>();
    private final Set<Integer> selectedPositions = new LinkedHashSet<>();

    public ImageAdapter(Context context, SelectionListener listener) {
        this.context = context;
        this.listener = listener;
    }

    public void setImages(List<Uri> uris) {
        images.clear();
        images.addAll(uris);
        selectedPositions.clear();
        notifyDataSetChanged();
    }

    public List<Uri> getSelectedImages() {
        List<Uri> result = new ArrayList<>();
        for (int pos : selectedPositions) {
            result.add(images.get(pos));
        }
        return result;
    }

    public void selectAll() {
        selectedPositions.clear();
        for (int i = 0; i < images.size(); i++) {
            selectedPositions.add(i);
        }
        notifyDataSetChanged();
        listener.onSelectionChanged(selectedPositions.size());
    }

    public void deselectAll() {
        selectedPositions.clear();
        notifyDataSetChanged();
        listener.onSelectionChanged(0);
    }

    @NonNull
    @Override
    public ImageViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(context)
                .inflate(R.layout.item_image, parent, false);
        return new ImageViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ImageViewHolder holder, int position) {
        Uri uri = images.get(position);
        boolean selected = selectedPositions.contains(position);

        Glide.with(context)
                .load(uri)
                .centerCrop()
                .thumbnail(0.3f)
                .into(holder.imageView);

        holder.overlay.setVisibility(selected ? View.VISIBLE : View.GONE);
        holder.checkmark.setVisibility(selected ? View.VISIBLE : View.GONE);

        holder.itemView.setOnClickListener(v -> {
            int pos = holder.getAdapterPosition();
            if (pos == RecyclerView.NO_POSITION) return;
            if (selectedPositions.contains(pos)) {
                selectedPositions.remove(pos);
            } else {
                selectedPositions.add(pos);
            }
            notifyItemChanged(pos);
            listener.onSelectionChanged(selectedPositions.size());
        });
    }

    @Override
    public int getItemCount() {
        return images.size();
    }

    static class ImageViewHolder extends RecyclerView.ViewHolder {
        ImageView imageView;
        View overlay;
        ImageView checkmark;

        ImageViewHolder(@NonNull View itemView) {
            super(itemView);
            imageView = itemView.findViewById(R.id.image_view);
            overlay = itemView.findViewById(R.id.selection_overlay);
            checkmark = itemView.findViewById(R.id.checkmark);
        }
    }
}
