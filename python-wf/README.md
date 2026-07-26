# Lung Cancer Bulk RNA-Seq Data Analysis Pipeline in Python

A end-to-end computational biology workflow for analyzing bulk RNA-sequencing data from the Cancer Cell Line Encyclopedia (CCLE). This pipeline guides users from raw counts data processing and unsupervised exploratory analysis (PCA, hierarchical clustering) to differential expression modeling (`PyDESeq2`) and downstream functional pathway enrichment.

## Setup & Installation

### 1. Clone the Repository

Clone the repository to your local machine. This command checks out the `main` branch into a clean `lc-bulk-rnaseq` directory:

```bash
git clone https://github.com/paymantohidifar/lung-cancer-bulk-rnaseq-analysis --branch main lc-bulk-rnaseq
cd lc-bulk-rnaseq/python-wf

```

### 2. Local Environment Setup via `pixi`

Environment dependencies are managed using [Pixi](https://pixi.sh/) for reproducible, isolated environment builds inside a local `.pixi/` directory.

```bash
# Optional: Preview dependency resolution without installing packages
pixi update

# Install the default environment profile
pixi install

```

> **Platform Compatibility Note:**
> This setup supports **Linux (x86_64)**, **macOS (Apple Silicon / ARM64)**, and **Windows (64-bit)**. The primary workflow has been fully tested and verified on Linux (x86_64).


## Interactive Analysis Notebooks

The core pipeline is structured into sequential Jupyter notebooks covering data preparation through pathway enrichment:

1. [Data Acquisition & Preparation](./notebooks/1_prepare_data.ipynb) — Download raw count matrices and sample annotations and prepare them for downstream analysis.
2. [Count Normalization & VST](./notebooks/2_normalize_data.ipynb) — Apply size-factor normalization and variance-stabilizing transformations for EDA.
3. [Unsupervised Principal Component Analysis](./notebooks/3_pca_analysis.ipynb) — Map primary biological axes of variation.
4. [Hierarchical Clustering](./notebooks/4_hierarchical_clustering.ipynb) — Group cell lines into distinct molecular lineages using clustring and heatmaps.
5. [Differential Expression Analysis](./notebooks/5_differential_expression_analysis.ipynb) — Identify lineage markers using `PyDESeq2`.
6. [Functional Enrichment & Pathway Analysis](./notebooks/6_functional_enrichment_pathway_analysis.ipynb) — Perform ORA and GSEA (GO/KEGG).

*Check out the [`/bonus/`](./bonus/) directory for supplementary materials.*


## Snakemake Pipeline

*Coming soon.*


## AI Agents & Skills

*Coming soon.*


## Licensing

This repository is licensed under the [MIT License](../LICENSE).
