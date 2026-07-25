# src/utils/helpers.py
"""Utility functions for transcriptomic data processing, statistical testing, and visualization."""

from typing import Any, Dict, List, Optional, Tuple, Union

from itertools import combinations

from adjustText import adjust_text
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pydeseq2.dds import DeseqDataSet
from pydeseq2.default_inference import DefaultInference
import scanpy as sc
import scipy.stats as stats
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.multitest import multipletests


def sanitize_uns_metadata(adata: sc.AnnData) -> sc.AnnData:
    """Sanitize `.uns` metadata in an AnnData object to ensure HDF5 compatibility.

    Converts any pandas Series stored inside `adata.uns` into standard Python dictionaries.
    This prevents downstream HDF5 serialization/IO errors during file writes (`.write_h5ad()`).

    Parameters
    ----------
    adata : sc.AnnData
        Annotated data object whose unstructured metadata (`.uns`) requires sanitization.

    Returns
    -------
    sc.AnnData
        The modified `AnnData` object with serialized metadata dictionaries in `.uns`.
    """
    # Iterate over a key list copy to safely modify the dictionary in-place
    for key in list(adata.uns.keys()):
        if isinstance(adata.uns[key], pd.Series):
            adata.uns[key] = adata.uns[key].to_dict()
    return adata


def run_post_hoc_pairwise_pipeline(
    groups: Dict[str, Union[List[float], np.ndarray, pd.Series]], 
    alpha: float = 0.05
) -> Optional[List[Dict[str, Any]]]:
    """Execute an omnibus Kruskal-Wallis test followed by post-hoc Mann-Whitney U tests.

    Evaluates global significance across multiple groups using a non-parametric Kruskal-Wallis
    test. If significant at the specified `alpha` level, pairwise two-sided Mann-Whitney U tests
    are performed across all group combinations with multiple-testing adjustments via Bonferroni
    (Family-Wise Error Rate) and Benjamini-Hochberg (False Discovery Rate).

    Parameters
    ----------
    groups : Dict[str, Union[List[float], np.ndarray, pd.Series]]
        Mapping of group labels to 1D arrays or lists of numerical expression/metric values.
    alpha : float, optional
        Significance threshold for the omnibus test and multiple-testing filtering, by default 0.05.

    Returns
    -------
    Optional[List[Dict[str, Any]]]
        List of dictionaries containing pairwise statistical results (including raw, Bonferroni-adjusted,
        and Benjamini-Hochberg-adjusted $p$-values) for pairs meeting the FDR threshold (`p_adj_bh <= alpha`).
        Returns `None` if the omnibus test is non-significant or no pairwise comparison survives correction.
    """
    # Stage 1: Omnibus Test (Kruskal-Wallis)
    # Ensure a global variance exists before conducting pairwise testing
    kw_result = stats.kruskal(*groups.values())
    if kw_result.pvalue > alpha:
        return None

    # Stage 2: Pairwise Mann-Whitney U Tests
    pairs: List[Tuple[str, str]] = []
    raw_pvals: List[float] = []

    for label_a, label_b in combinations(groups.keys(), 2):
        _, p_val = stats.mannwhitneyu(
            groups[label_a], groups[label_b], alternative="two-sided"
        )
        pairs.append((label_a, label_b))
        raw_pvals.append(p_val)

    # Stage 3: Multiple-Testing Corrections
    # Familywise Error Rate (FWER) control via Bonferroni
    rej_bonf, p_bonf, _, _ = multipletests(
        raw_pvals, alpha=alpha, method="bonferroni"
    )

    # False Discovery Rate (FDR) control via Benjamini-Hochberg
    rej_bh, p_bh, _, _ = multipletests(raw_pvals, alpha=alpha, method="fdr_bh")

    # Stage 4: Compile Significant Pairwise Outputs
    results: List[Dict[str, Any]] = []
    zipped_data = zip(pairs, raw_pvals, rej_bonf, p_bonf, rej_bh, p_bh)

    for pair, p_raw, r_bonf, p_adjusted_bonf, r_bh, p_adjusted_bh in zipped_data:
        # Filter: Retain only comparisons that survive FDR control at the given alpha threshold
        if p_adjusted_bh <= alpha:
            results.append(
                {
                    "pairs": pair,
                    "p_raw": float(round(p_raw, 4)),
                    "bonferroni_reject": bool(r_bonf),
                    "p_adj_bonferroni": float(round(p_adjusted_bonf, 4)),
                    "bh_reject": bool(r_bh),
                    "p_adj_bh": float(round(p_adjusted_bh, 4)),
                }
            )

    return results if results else None


def prepare_vst_data(
    counts_filepath: str,
    meta_filepath: str,
    top_n_genes: int = 100,
    design: str = "~Pathology",
    vst_filepath: Optional[str] = None,
    write_to_disk: bool = True,
    n_cpus: int = 6,
) -> DeseqDataSet:
    """Load raw RNA-seq counts, filter low-coverage genes, and compute VST normalized counts.

    Reads gene expression count matrices and sample metadata, filters out low-expressed genes
    based on a minimum aggregate count threshold, constructs a `PyDESeq2.DeseqDataSet`, and applies 
    Variance Stabilizing Transformation (VST). Sanitizes output `.uns` metadata and optionally caches 
    the resulting AnnData object to an `.h5ad` file.

    Parameters
    ----------
    counts_filepath : str
        Path to the raw expression counts CSV file (oriented as genes x samples).
    meta_filepath : str
        Path to the sample metadata CSV file (oriented as samples x covariates).
    top_n_genes : int, optional
        Minimum sum of raw counts across all samples required to retain a gene, by default 100.
    design : str, optional
        Experimental design formula for `DeseqDataSet`, by default "~Pathology".
    vst_filepath : Optional[str], optional
        Output file path for saving the transformed `h5ad` file if `write_to_disk=True`, by default None.
    write_to_disk : bool, optional
        Whether to export the transformed `DeseqDataSet` object to disk, by default True.
    n_cpus : int, optional
        Number of CPU cores allocated for parallel inference in PyDESeq2, by default 6.

    Returns
    -------
    DeseqDataSet
        The initialized and VST-transformed `DeseqDataSet` container object.
    """
    # Load raw RNA-seq counts and transpose to samples x genes layout
    counts_subset = pd.read_csv(counts_filepath, header=0, index_col=0)
    counts_subset.index.name = "Gene"
    keep = counts_subset.sum(axis="columns") >= top_n_genes
    counts_subset = counts_subset[keep].copy()
    counts_subset = counts_subset.transpose().astype(int)

    # Load associated sample metadata
    meta_subset = pd.read_csv(meta_filepath, header=0, index_col=0)

    # Initialize PyDESeq2 parallel processing inference engine
    inference = DefaultInference(n_cpus=n_cpus)

    # Initialize DeseqDataSet container with outlier handling enabled
    dds = DeseqDataSet(
        counts=counts_subset,
        metadata=meta_subset,
        design=design,
        refit_cooks=True,  # Detect and replace extreme count outliers using Cook's distance
        inference=inference,
    )

    # Perform Variance Stabilizing Transformation (blind to design covariates)
    dds.vst(use_design=False, fit_type="parametric")

    # Sanitize metadata to prevent HDF5 serialization errors and save if requested
    dds = sanitize_uns_metadata(dds)
    if write_to_disk:
        if vst_filepath is None:
            raise ValueError("`vst_filepath` must be specified when `write_to_disk=True`.")
        dds.write_h5ad(vst_filepath, compression="gzip")
        print(f"Pipeline complete. VST object cached to: {vst_filepath}")
    else:
        print("Pipeline complete. VST object retained in memory (not saved to disk).")

    return dds


def plot_volcano(
    df: pd.DataFrame,
    lfc_col: str = "log2FoldChange",
    padj_col: str = "padj",
    gene_col: str = "gene_name",
    lfc_thresh: float = 1.0,
    padj_thresh: float = 0.05,
    top_n_labels: int = 15,
    lab_size: int = 7,
    select_labs: Optional[List[str]] = None,
    title: str = "Volcano Plot",
    figsize: Tuple[int, int] = (8, 6),
) -> Tuple[plt.Figure, plt.Axes]:
    """Generate a publication-ready volcano plot for differential expression results.

    Visualizes log2 fold changes against -$log_{10}$ adjusted $p$-values. Categorizes genes into
    statistically significant upregulated, downregulated, or non-significant cohorts, and automatically
    repels gene labels to avoid text overlap using `adjustText`.

    Parameters
    ----------
    df : pd.DataFrame
        Differential expression results table containing fold-change and adjusted p-value columns.
    lfc_col : str, optional
        Column name holding $\\log_2$ fold-change values, by default "log2FoldChange".
    padj_col : str, optional
        Column name holding adjusted $p$-values / FDR values, by default "padj".
    gene_col : str, optional
        Column name holding gene symbols/identifiers for labeling, by default "gene_name".
    lfc_thresh : float, optional
        Absolute $\\log_2$ fold-change significance threshold, by default 1.0.
    padj_thresh : float, optional
        Adjusted $p$-value significance threshold, by default 0.05.
    top_n_labels : int, optional
        Number of top significant DEGs to label when `select_labs` is None, by default 15.
    lab_size : int, optional
        Font size for repelled gene label text, by default 7.
    select_labs : Optional[List[str]], optional
        Explicit list of gene identifiers to label, overriding `top_n_labels`, by default None.
    title : str, optional
        Plot title header, by default "Volcano Plot".
    figsize : Tuple[int, int], optional
        Width and height dimensions for the figure canvas, by default (8, 6).

    Returns
    -------
    Tuple[plt.Figure, plt.Axes]
        Matplotlib figure and axes objects containing the formatted volcano plot.
    """
    fig, ax = plt.subplots(figsize=figsize)

    df = df.copy().reset_index()

    if "Description" in df.columns:
        df = df.rename(columns={"Description": "Gene"}, errors="ignore")

    # Transform padj values to -log10 scale; handle zero padj edge cases cleanly
    df["-log10_padj"] = -np.log10(df[padj_col].replace(0, np.nan))
    df["-log10_padj"] = df["-log10_padj"].fillna(df["-log10_padj"].max() + 2)

    # Define significance boundaries and assign categorical labels
    conditions = [
        (df[padj_col] < padj_thresh) & (df[lfc_col] > lfc_thresh),
        (df[padj_col] < padj_thresh) & (df[lfc_col] < -lfc_thresh),
        (df[padj_col] < padj_thresh) & (df[lfc_col].abs() <= lfc_thresh),
    ]
    choices = ["Up-regulated", "Down-regulated", "Significant (LFC low)"]
    df["Category"] = np.select(conditions, choices, default="Not Significant")

    # Color palette matching standard publication themes
    palette = {
        "Up-regulated": "#E41A1C",          # Red
        "Down-regulated": "#377EB8",        # Blue
        "Significant (LFC low)": "#4DAF4A",  # Green
        "Not Significant": "#999999",        # Grey
    }

    # Render scatter plot points
    sns.scatterplot(
        data=df,
        x=lfc_col,
        y="-log10_padj",
        hue="Category",
        palette=palette,
        alpha=0.75,
        s=20,
        ax=ax,
    )

    # Draw reference cutoffs
    ax.axvline(x=lfc_thresh, color="black", linestyle="--", linewidth=1, alpha=0.7)
    ax.axvline(x=-lfc_thresh, color="black", linestyle="--", linewidth=1, alpha=0.7)
    ax.axhline(
        y=-np.log10(padj_thresh), color="black", linestyle="--", linewidth=1, alpha=0.7
    )

    # Filter target genes for text annotation
    if select_labs is None:
        sig_genes = (
            df[df["Category"].isin(["Up-regulated", "Down-regulated"])]
            .sort_values(padj_col)
            .head(top_n_labels)
        )
    else:
        sig_genes = df[df["Gene"].isin(select_labs)]

    # Populate text instances for auto-repelling
    texts = []
    for _, row in sig_genes.iterrows():
        texts.append(
            ax.text(
                row[lfc_col],
                row["-log10_padj"],
                row[gene_col],
                fontsize=lab_size,
                weight="bold",
            )
        )

    # Adjust overlapping text labels automatically
    adjust_text(texts, arrowprops=dict(arrowstyle="-", color="black", lw=0.5))

    # Axis labels and typography formatting
    ax.set_xlabel(r"$\log_2$ Fold Change", fontsize=14)
    ax.set_ylabel(r"$-\log_{10}$ Adjusted $p$-value", fontsize=14)
    ax.set_title(title, fontsize=16, weight="bold")
    ax.legend(title="", bbox_to_anchor=(1.05, 1), loc="upper left")

    plt.tight_layout()
    return fig, ax