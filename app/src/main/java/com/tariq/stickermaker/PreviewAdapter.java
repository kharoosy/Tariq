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

import java.util.List;

/** Small adapter for the preview strip in StickerPackActivity. */
public class PreviewAdapter extends RecyclerView.Adapter<PreviewAdapter.VH> {

    private final Context context;
    private final List<Uri> uris;

    public PreviewAdapter(Context context, List<Uri> uris) {
        this.context = context;
        this.uris    = uris;
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(context)
                .inflate(R.layout.item_preview, parent, false);
        return new VH(v);
    }

    @Override
    public void onBindViewHolder(@NonNull VH holder, int position) {
        Glide.with(context)
                .load(uris.get(position))
                .centerCrop()
                .into(holder.image);
    }

    @Override
    public int getItemCount() { return uris.size(); }

    static class VH extends RecyclerView.ViewHolder {
        ImageView image;
        VH(@NonNull View itemView) {
            super(itemView);
            image = itemView.findViewById(R.id.preview_image);
        }
    }
}
