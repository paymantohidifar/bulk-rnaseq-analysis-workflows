# src/utils/helpers.py
"""Utility functions for transcriptomic data processing."""

import pandas as pd
import scipy.stats as stats
from itertools import combinations
from statsmodels.stats.multitest import multipletests
from pydeseq2.dds import DeseqDataSet
from pydeseq2.default_inference import DefaultInference
import scanpy as sc

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist
from sklearn.preprocessing import StandardScaler


def sanitize_uns_metadata(adata):
    """Convert unsupported pandas Series in .uns to dictionaries to prevent HDF5 IO errors."""
    # Loop over a copy of keys to safely modify the dictionary in-place
    for key in list(adata.uns.keys()):
        if isinstance(adata.uns[key], pd.Series):
            adata.uns[key] = adata.uns[key].to_dict()
    return adata


def run_post_hoc_pairwise_pipeline(groups, alpha=0.05):
    """Execute a non-parametric omnibus Kruskal-Wallis test followed by
    pairwise Mann-Whitney U post-hoc tests with multiple-testing corrections.
    """
    # Stage 1: Run Omnibus Test (Kruskal-Wallis)
    # Ensures a global difference exists before conducting pairwise testing
    kw_result = stats.kruskal(*groups.values())
    if kw_result.pvalue > alpha:
        return None

    # Stage 2: Conduct Pairwise Mann-Whitney U Tests
    pairs = []
    raw_pvals = []

    for label_a, label_b in combinations(groups.keys(), 2):
        _, p_val = stats.mannwhitneyu(
            groups[label_a], groups[label_b], alternative="two-sided"
        )
        pairs.append((label_a, label_b))
        raw_pvals.append(p_val)

    # Stage 3: Multiple-Testing Corrections
    # Familywise Error Rate (FWER) control via Bonferroni (strict)
    rej_bonf, p_bonf, _, _ = multipletests(
        raw_pvals, alpha=alpha, method="bonferroni"
    )

    # False Discovery Rate (FDR) control via Benjamini-Hochberg (discovery-oriented)
    rej_bh, p_bh, _, _ = multipletests(raw_pvals, alpha=alpha, method="fdr_bh")

    # Stage 4: Compile Signficant Outputs
    results = []
    zipped_data = zip(pairs, raw_pvals, rej_bonf, p_bonf, rej_bh, p_bh)

    for pair, p_raw, r_bonf, p_adjusted_bonf, r_bh, p_adjusted_bh in zipped_data:
        # Filter results: Only return pairs that remain significant under the FDR threshold
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


def prepare_vst_data(counts_filepath, meta_filepath, top_n_genes=100, design="~Pathology", vst_filepath=None, write_to_disk=True, n_cpus=6):
    """Prepare VST data for downstream analysis.
    Args:
        counts_filepath: Path to the counts file.
        meta_filepath: Path to the metadata file.
        top_n_genes: Top N genes to keep.
        design: Design formula.
        vst_filepath: Path to the VST file.
        n_cpus: Number of CPUs to use.
    """
    
    # Load and prepare the raw RNA-seq count
    counts_subset = pd.read_csv(counts_filepath, header=0, index_col=0)   
    counts_subset.index.name = 'Gene'
    keep = (counts_subset.sum(axis='columns') >= top_n_genes)
    counts_subset = counts_subset[keep].copy()
    counts_subset = counts_subset.transpose().astype(int)

    # Load the associated sample metadata (e.g., cell line names, pathology, etc.)
    meta_subset = pd.read_csv(meta_filepath, header=0, index_col=0)

    
    
    # Initialize inference engine with parallel processing
    inference = DefaultInference(n_cpus=n_cpus)

    # Initialize the DeseqDataSet with a pathology-based experimental design
    dds = DeseqDataSet(
        counts=counts_subset,
        metadata=meta_subset,
        design=design,
        refit_cooks=True,  # Detect and replace outliers using Cook's distance
        inference=inference,
    )

    # Run the dispersion estimation and normalization pipeline
    dds.deseq2()
    dds.vst()  

    # Sanitize metadata to prevent HDF5 serialization errors, then write to disk
    dds = sanitize_uns_metadata(dds)
    if write_to_disk:
        dds.write_h5ad(vst_filepath, compression="gzip")
        print(f"Pipeline complete. VST object cached to: {vst_filepath}")
    else:
        print("Pipeline complete. VST object not cached to disk.")

    return dds