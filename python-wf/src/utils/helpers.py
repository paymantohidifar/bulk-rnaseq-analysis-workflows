# src/utils/helpers.py
"""Utility functions for transcriptomic data processing."""

import pandas as pd
import scipy.stats as stats
from itertools import combinations
from statsmodels.stats.multitest import multipletests


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
