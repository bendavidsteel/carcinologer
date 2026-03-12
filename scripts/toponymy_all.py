from pathlib import Path

import polars as pl
import toponymy
import toponymy.embedding_wrappers
import toponymy.llm_wrappers
import parampacmap

DATA_DIR = Path('./data')


def main():
    filenames = ['all_posts.parquet', 'submolt_posts.parquet', 'search_results.parquet', 'agent_posts.parquet']
    posts_df = pl.concat([pl.read_parquet(DATA_DIR / filename) for filename in filenames], how='diagonal_relaxed').unique('id')
    comments_df = pl.read_parquet(DATA_DIR / 'comments.parquet')

    posts_df = posts_df.with_columns(
        pl.concat_str([pl.col('title'), pl.lit('\n\n'), pl.col('content').fill_null('')], ignore_nulls=True).alias('text'),
        pl.lit('post').alias('type'),
    ).select(['id', 'text', 'type', 'created_at', 'upvotes', 'downvotes'])

    comments_df = comments_df.with_columns(
        pl.col('content').alias('text'),
        pl.lit('comment').alias('type'),
    ).select(['id', 'text', 'type', 'created_at', 'upvotes', 'downvotes'])

    df = pl.concat([posts_df, comments_df], how='diagonal_relaxed')
    print(f"Total documents: {df.shape[0]} ({posts_df.shape[0]} posts, {comments_df.shape[0]} comments)")

    texts = df['text'].fill_null('').to_list()

    embedding_model_name = 'intfloat/multilingual-e5-small'
    max_model_len = 512
    embedding_model = toponymy.embedding_wrappers.VLLMEmbedder(
        embedding_model_name,
        kwargs={'gpu_memory_utilization': 0.1, 'max_model_len': max_model_len}
    )

    short_texts = df['text'].fill_null('').str.slice(0, max_model_len).to_list()
    embeddings = embedding_model.encode(short_texts, show_progress_bar=True)

    umap_model = parampacmap.ParamPaCMAP(
        n_components=2,
        verbose=True
    )
    umap_vectors = umap_model.fit_transform(embeddings)

    llm_model_name = 'Qwen/Qwen3-4B'
    llm = toponymy.llm_wrappers.AsyncVLLM(llm_model_name, gpu_memory_utilization=0.7, max_model_len=8192)

    base_min_cluster_size = max(10, len(texts) // 50)
    clusterer = toponymy.ToponymyClusterer(min_clusters=4, verbose=True, base_min_cluster_size=base_min_cluster_size)
    clusterer.fit(clusterable_vectors=umap_vectors, embedding_vectors=embeddings)

    topic_model = toponymy.Toponymy(
        llm_wrapper=llm,
        text_embedding_model=embedding_model,
        clusterer=clusterer,
        object_description="moltbook posts and comments",
        corpus_description="moltbook social media dataset",
    )

    topic_model.fit(texts, embeddings, umap_vectors)

    topic_df = df.with_columns(
        [pl.Series(name=f"cluster_layer_{i}", values=c.topic_name_vector) for i, c in enumerate(topic_model.cluster_layers_)]
    ).with_columns(
        pl.Series(name='umap_vector', values=umap_vectors),
    )

    topic_df.write_parquet(DATA_DIR / 'moltbook_topics.parquet.zstd')
    print(f"Saved topics to {DATA_DIR / 'moltbook_topics.parquet.zstd'}")


if __name__ == '__main__':
    main()