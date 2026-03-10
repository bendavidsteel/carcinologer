from pathlib import Path

import datamapplot
import polars as pl

DATA_DIR = Path('./data')


def main():
    topic_df = pl.read_parquet(DATA_DIR / 'moltbook_topics.parquet.zstd')

    title = 'Moltbook Posts and Comments'

    topic_cols = [col for col in topic_df.columns if col.startswith('cluster_layer_')]

    max_text_len = 100

    topic_df = topic_df.with_columns(
        pl.col('created_at').str.to_datetime().alias('created_at_dt'),
        (1 + pl.col('upvotes').fill_null(0) - pl.col('downvotes').fill_null(0)).clip(1, None).log1p().alias('score_log'),
        pl.when(pl.col('text').str.len_chars() > max_text_len) \
            .then(pl.format("{}...", pl.col('text').str.slice(0, max_text_len))) \
            .otherwise(pl.col('text')) \
            .alias('hover_text'),
    )

    plot = datamapplot.create_interactive_plot(
        topic_df['umap_vector'].to_numpy(),
        *[topic_df[col].to_numpy() for col in topic_cols],
        hover_text=topic_df['hover_text'].to_numpy(),
        title=title,
        enable_search=True,
        darkmode=True,
        marker_size_array=topic_df['score_log'].to_numpy(),
        font_family="Cinzel",
        minify_deps=True,
        histogram_data=topic_df['created_at_dt'].to_numpy(),
        histogram_group_datetime_by='hour',
    )

    output_path = DATA_DIR / 'moltbook_topics.html'
    plot.save(str(output_path))
    print(f"Saved plot to {output_path}")


if __name__ == "__main__":
    main()