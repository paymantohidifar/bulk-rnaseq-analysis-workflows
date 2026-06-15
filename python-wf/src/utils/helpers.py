# src/utils/helpers.py
"""Utility functions for transcriptomic data processing."""

import pandas as pd

def sanitize_uns_metadata(adata):
    """Convert unsupported pandas Series in .uns to dictionaries to prevent HDF5 IO errors."""
    # Loop over a copy of keys to safely modify the dictionary in-place
    for key in list(adata.uns.keys()):
        if isinstance(adata.uns[key], pd.Series):
            adata.uns[key] = adata.uns[key].to_dict()
    return adata