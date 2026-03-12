#!/usr/bin/env python
"""
Temporal Data Map Pipeline

Combines temporal-mapper for temporal clustering, toponymy for LLM-based
cluster naming, and datamapplot for interactive visualization with time
on x-axis and a 1D PaCMAP semantic dimension on y-axis.
"""
from pathlib import Path

import numpy as np
import polars as pl

import datamapplot

DATA_DIR = Path('/home/ndg/users/bsteel2/repos/carcinologer/data')
OUTPUT_PATH = DATA_DIR / 'temporal_datamap.html'
LABELS_CACHE = DATA_DIR / 'temporal_topic_labels.parquet'


def assign_temporal_clusters(mapper, n_docs):
    """Assign each document to its best temporal cluster.

    For each document, try checkpoints in order of weight. Take the first
    checkpoint where the document has a real cluster (not noise -1 or
    unassigned -2). Fall back to the highest-weight checkpoint.
    """
    sorted_cps = np.argsort(-mapper.weights, axis=0)

    doc_cluster_ids = np.full(n_docs, -2, dtype=int)
    doc_checkpoint = np.zeros(n_docs, dtype=int)

    for i in range(n_docs):
        for rank in range(mapper.N_checkpoints):
            cp = sorted_cps[rank, i]
            cl = mapper.clusters[cp, i]
            if cl >= 0:
                doc_cluster_ids[i] = cl
                doc_checkpoint[i] = cp
                break
        else:
            cp = sorted_cps[0, i]
            doc_cluster_ids[i] = mapper.clusters[cp, i]
            doc_checkpoint[i] = cp

    return doc_cluster_ids, doc_checkpoint


def build_datetime_axis_js(time_min_ms, time_max_ms, deck_x_min, deck_x_max):
    """Build the custom JS/HTML/CSS for a datetime x-axis overlay synced to Deck.GL."""

    axis_css = """
      #time-axis {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        height: 48px;
        pointer-events: none;
        z-index: 10;
      }
      #time-axis svg {
        width: 100%;
        height: 100%;
      }
      #time-axis .tick-line {
        stroke: rgba(255,255,255,0.3);
        stroke-width: 1;
      }
      #time-axis .tick-label {
        fill: rgba(255,255,255,0.8);
        font-family: monospace;
        font-size: 11px;
        text-anchor: middle;
        dominant-baseline: hanging;
      }
      #time-axis .axis-line {
        stroke: rgba(255,255,255,0.25);
        stroke-width: 1;
      }
    """

    axis_html = '<div id="time-axis"><svg></svg></div>'

    # The tick intervals to choose from (in ms), from coarse to fine
    axis_js = f"""
    (function() {{
      const TIME_MIN_MS = {time_min_ms};
      const TIME_MAX_MS = {time_max_ms};
      const DECK_X_MIN = {deck_x_min};
      const DECK_X_MAX = {deck_x_max};

      // Linear mapping: deck x -> epoch ms
      function deckXToMs(dx) {{
        return TIME_MIN_MS + (dx - DECK_X_MIN) / (DECK_X_MAX - DECK_X_MIN) * (TIME_MAX_MS - TIME_MIN_MS);
      }}

      // Tick intervals in ms
      const INTERVALS = [
        {{ ms: 365.25*24*3600000, label: 'year' }},
        {{ ms: 30*24*3600000, label: 'month' }},
        {{ ms: 7*24*3600000, label: 'week' }},
        {{ ms: 24*3600000, label: 'day' }},
        {{ ms: 12*3600000, label: '12h' }},
        {{ ms: 6*3600000, label: '6h' }},
        {{ ms: 3*3600000, label: '3h' }},
        {{ ms: 3600000, label: '1h' }},
        {{ ms: 1800000, label: '30m' }},
        {{ ms: 600000, label: '10m' }},
        {{ ms: 300000, label: '5m' }},
        {{ ms: 60000, label: '1m' }},
      ];

      const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

      function formatTick(ms, intervalLabel) {{
        const d = new Date(ms);
        const mon = MONTHS[d.getUTCMonth()];
        const day = d.getUTCDate();
        const hh = String(d.getUTCHours()).padStart(2,'0');
        const mm = String(d.getUTCMinutes()).padStart(2,'0');

        if (intervalLabel === 'year') return d.getUTCFullYear().toString();
        if (intervalLabel === 'month') return mon + ' ' + d.getUTCFullYear();
        if (intervalLabel === 'week' || intervalLabel === 'day')
          return mon + ' ' + day;
        // sub-day: show date + time
        return mon + ' ' + day + ' ' + hh + ':' + mm;
      }}

      function pickInterval(visibleRangeMs, screenWidth) {{
        // Aim for ~6-12 ticks
        const targetTicks = Math.max(4, Math.min(12, Math.floor(screenWidth / 120)));
        for (const iv of INTERVALS) {{
          const n = visibleRangeMs / iv.ms;
          if (n >= targetTicks * 0.4 && n <= targetTicks * 3) return iv;
        }}
        return INTERVALS[INTERVALS.length - 1];
      }}

      function renderAxis(viewState) {{
        const svg = document.querySelector('#time-axis svg');
        if (!svg || !viewState) return;

        const w = svg.clientWidth;
        const h = svg.clientHeight;
        if (w === 0) return;

        // Build a viewport to project data coords -> screen coords
        const vp = new deck.WebMercatorViewport({{
          width: w,
          height: document.documentElement.clientHeight,
          longitude: viewState.longitude,
          latitude: viewState.latitude,
          zoom: viewState.zoom,
        }});

        // Visible data x range via unproject at screen edges
        const leftX = vp.unproject([0, 0])[0];
        const rightX = vp.unproject([w, 0])[0];

        const leftMs = deckXToMs(leftX);
        const rightMs = deckXToMs(rightX);
        const rangeMs = rightMs - leftMs;

        if (rangeMs <= 0 || !isFinite(rangeMs)) return;

        const interval = pickInterval(rangeMs, w);

        // Snap first tick to interval boundary
        const firstTick = Math.ceil(leftMs / interval.ms) * interval.ms;

        let ticksHtml = '';
        // Axis baseline
        ticksHtml += '<line class="axis-line" x1="0" y1="0" x2="' + w + '" y2="0"/>';

        for (let t = firstTick; t <= rightMs; t += interval.ms) {{
          // Map ms -> deck x -> screen x
          const dx = DECK_X_MIN + (t - TIME_MIN_MS) / (TIME_MAX_MS - TIME_MIN_MS) * (DECK_X_MAX - DECK_X_MIN);
          const screenX = vp.project([dx, viewState.latitude])[0];

          if (screenX < -50 || screenX > w + 50) continue;

          const label = formatTick(t, interval.label);
          ticksHtml += '<line class="tick-line" x1="' + screenX + '" y1="0" x2="' + screenX + '" y2="8"/>';
          ticksHtml += '<text class="tick-label" x="' + screenX + '" y="12">' + label + '</text>';
        }}

        svg.innerHTML = ticksHtml;
      }}

      // Hook into Deck.GL view state changes
      const origOnViewStateChange = datamap.deckgl.props.onViewStateChange;
      datamap.deckgl.setProps({{
        onViewStateChange: (params) => {{
          if (origOnViewStateChange) origOnViewStateChange(params);
          renderAxis(params.viewState);
        }}
      }});

      // Initial render after a short delay for Deck.GL to settle
      setTimeout(() => {{
        const vs = datamap.deckgl.viewManager
          ? datamap.deckgl.viewManager.getViewState()
          : null;
        if (vs) renderAxis(vs);
      }}, 1000);

      // Also re-render on resize
      window.addEventListener('resize', () => {{
        const vs = datamap.deckgl.viewManager
          ? datamap.deckgl.viewManager.getViewState()
          : null;
        if (vs) renderAxis(vs);
      }});
    }})();
    """

    return axis_css, axis_html, axis_js


def main():
    # ─── Load data ───────────────────────────────────────────────────────
    print("Loading data...")
    topic_df = pl.read_parquet(DATA_DIR / 'moltbook_topics.parquet.zstd')
    print(f"  {topic_df.shape[0]} documents")

    topic_df = topic_df.with_columns(
        pl.col('created_at').str.to_datetime(time_zone='UTC').alias('created_at_dt'),
    )
    epoch_seconds = topic_df['created_at_dt'].dt.epoch('s').to_numpy().astype(np.float64)
    time_numeric = epoch_seconds - epoch_seconds.min()

    # Raw embeddings (384d)
    print("Loading embeddings...")
    embeddings = pl.read_parquet(DATA_DIR / 'embeddings.parquet.zstd').to_numpy()

    # ─── 1D PaCMAP: 384d → 1d semantic axis ─────────────────────────────
    pacmap_1d_cache = DATA_DIR / 'pacmap_1d.npy'
    if pacmap_1d_cache.exists():
        print(f"  Loading cached 1D PaCMAP from {pacmap_1d_cache}")
        semantic_y = np.load(pacmap_1d_cache)
    else:
        import pacmap
        print("  Computing 1D PaCMAP (384d → 1d)...")
        reducer = pacmap.PaCMAP(n_components=1, verbose=True)
        semantic_y = reducer.fit_transform(embeddings).ravel()
        np.save(pacmap_1d_cache, semantic_y)
        print(f"  Cached to {pacmap_1d_cache}")

    # ─── Clustering + naming (cached) ──────────────────────────────────
    n_docs = len(time_numeric)

    if LABELS_CACHE.exists():
        print(f"Loading cached topic labels from {LABELS_CACHE}")
        labels_df = pl.read_parquet(LABELS_CACHE)
        topic_labels = labels_df['topic_label'].to_numpy()
        print(f"  {len(np.unique(topic_labels))} unique topic names")
    else:
        from temporalmapper import TemporalMapper
        from temporalmapper.kernels import gaussian
        from fast_hdbscan import HDBSCAN
        import toponymy
        import toponymy.embedding_wrappers
        import toponymy.llm_wrappers
        from toponymy.clustering import centroids_from_labels, build_cluster_tree
        from toponymy.cluster_layer import ClusterLayerText

        # ─── Run TemporalMapper on the 1D semantic axis ──────────────────
        print("Running TemporalMapper (clustering on 1D PaCMAP)...")
        clusterer = HDBSCAN(min_cluster_size=15, min_samples=3)
        mapper = TemporalMapper(
            time=time_numeric,
            data=semantic_y.reshape(-1, 1).copy(),
            clusterer=clusterer,
            N_checkpoints=20,
            overlap=0.7,
            kernel=gaussian,
            slice_method="data",
            verbose=True,
        )
        mapper.fit()
        print(f"  Graph: {len(mapper.G.nodes())} nodes, {len(mapper.G.edges())} edges")

        # ─── Assign each document to a temporal cluster ──────────────────
        print("Assigning documents to temporal clusters...")
        doc_cluster_ids, doc_checkpoint = assign_temporal_clusters(mapper, n_docs)

        node_strings = np.array([
            f"{doc_checkpoint[i]}:{doc_cluster_ids[i]}" for i in range(n_docs)
        ])
        noise_mask = doc_cluster_ids < 0

        unique_nodes = np.unique(node_strings[~noise_mask])
        node_to_int = {node: i for i, node in enumerate(unique_nodes)}
        cluster_labels = np.full(n_docs, -1, dtype=np.intp)
        for i in range(n_docs):
            if not noise_mask[i]:
                cluster_labels[i] = node_to_int[node_strings[i]]

        n_labelled = (~noise_mask).sum()
        n_clusters = len(unique_nodes)
        print(f"  {n_labelled}/{n_docs} documents assigned ({n_labelled/n_docs*100:.0f}%)")
        print(f"  {n_clusters} temporal clusters")

        # ─── Name temporal clusters using Toponymy ───────────────────────
        print("Setting up Toponymy for cluster naming...")

        embedding_model_name = 'intfloat/multilingual-e5-small'
        max_model_len = 512
        embedding_model = toponymy.embedding_wrappers.VLLMEmbedder(
            embedding_model_name,
            kwargs={'gpu_memory_utilization': 0.1, 'max_model_len': max_model_len},
        )

        llm_model_name = 'Qwen/Qwen3-4B-Instruct-2507'
        llm = toponymy.llm_wrappers.AsyncVLLM(
            llm_model_name,
            gpu_memory_utilization=0.7,
            max_model_len=11000,
        )

        centroid_vectors = centroids_from_labels(cluster_labels, embeddings)

        layer = ClusterLayerText(
            cluster_labels=cluster_labels,
            centroid_vectors=centroid_vectors,
            layer_id=0,
            text_embedding_model=embedding_model,
        )
        cluster_tree = build_cluster_tree(np.array([cluster_labels]))

        pre_clusterer = toponymy.ToponymyClusterer()
        pre_clusterer.cluster_layers_ = [layer]
        pre_clusterer.cluster_tree_ = cluster_tree

        print("Running Toponymy topic naming...")
        topic_model = toponymy.Toponymy(
            llm_wrapper=llm,
            text_embedding_model=embedding_model,
            clusterer=pre_clusterer,
            object_description="social media posts and comments",
            corpus_description="social media dataset from Moltbook",
        )

        texts = topic_df['text'].fill_null('').str.slice(0, 800).to_list()
        topic_model.fit(texts, embeddings, semantic_y.reshape(-1, 1))

        label_layer = topic_model.cluster_layers_[0]
        topic_labels = np.array(label_layer.topic_name_vector)
        print(f"  Generated {len(np.unique(topic_labels))} unique topic names")

        # Cache the labels
        pl.DataFrame({'topic_label': topic_labels}) \
            .write_parquet(LABELS_CACHE)
        print(f"  Cached to {LABELS_CACHE}")

    # ─── Prepare coordinates ─────────────────────────────────────────────
    print("Preparing visualization coordinates...")

    # X = time (days since start), stretched to fill width
    x_days = time_numeric / 86400.0
    x_min, x_max = x_days.min(), x_days.max()
    x_normed = (x_days - x_min) / (x_max - x_min) * 30  # [0, 30]

    # Y = 1D PaCMAP semantic axis, scaled to ~half height so x dominates
    y_min, y_max = semantic_y.min(), semantic_y.max()
    y_normed = (semantic_y - y_min) / (y_max - y_min) * 18  # [0, 18]

    coords = np.column_stack([x_normed, y_normed])

    # After datamapplot rescaling: (30/max(30,18)) * (coords - mean)
    # x: (30/30)*(x - 15) -> [-15, 15]
    # y: (30/30)*(y - 9) -> [-9, 9]
    # So the deck.gl x range will be [-15, 15]
    deck_x_min = -15.0
    deck_x_max = 15.0

    # Epoch ms for the time axis
    time_min_ms = float(epoch_seconds.min()) * 1000
    time_max_ms = float(epoch_seconds.max()) * 1000

    # ─── Build datetime axis overlay ─────────────────────────────────────
    axis_css, axis_html, axis_js = build_datetime_axis_js(
        time_min_ms, time_max_ms, deck_x_min, deck_x_max
    )

    # ─── Prepare hover text ──────────────────────────────────────────────
    max_text_len = 200
    topic_df = topic_df.with_columns(
        pl.when(pl.col('text').str.len_chars() > max_text_len)
            .then(pl.format("{}...", pl.col('text').str.slice(0, max_text_len)))
            .otherwise(pl.col('text'))
            .alias('hover_text'),
    )
    hover_text = topic_df['hover_text'].to_numpy()

    # ─── Create interactive plot ─────────────────────────────────────────
    print("Creating interactive plot...")
    plot = datamapplot.create_interactive_plot(
        coords,
        topic_labels,
        hover_text=hover_text,
        title='Temporal Data Map: Moltbook',
        sub_title='Time \u2192 | Semantic \u2191',
        enable_search=True,
        darkmode=True,
        font_family="Cinzel",
        noise_label="Unlabelled",
        minify_deps=True,
        custom_css=axis_css,
        custom_html=axis_html,
        custom_js=axis_js,
    )

    plot.save(str(OUTPUT_PATH))
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
