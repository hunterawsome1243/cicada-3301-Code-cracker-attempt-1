"""Statistical fingerprint of a rune stream: IoC, entropy, chi-square, doublets,
periodic IoC / kappa scans and the cross-section shared-keystream scan."""

from __future__ import annotations

from runeforge.stats.basic import (
    chi2_uniform,
    coincidence_z,
    counts,
    doublet_count,
    doublet_stats,
    entropy_bits,
    ioc,
    ioc_norm,
    ioc_null_sd,
    summary,
)
from runeforge.stats.crosskey import diff_ioc_by_shift, familywise, shared_key_scan, z_to_p
from runeforge.stats.periodic import familywise_z, kappa, periodic_ioc, scan

__all__ = [
    "chi2_uniform",
    "coincidence_z",
    "counts",
    "diff_ioc_by_shift",
    "doublet_count",
    "doublet_stats",
    "entropy_bits",
    "familywise",
    "familywise_z",
    "ioc",
    "ioc_norm",
    "ioc_null_sd",
    "kappa",
    "periodic_ioc",
    "scan",
    "shared_key_scan",
    "summary",
    "z_to_p",
]
