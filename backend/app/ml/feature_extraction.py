"""Feature extraction from BB84/B92 simulation results for attack classifiers.

Each run becomes one fixed-length numeric feature vector. The features fall
into three families, chosen to separate the three attack signatures:

- **QBER family**: the headline error rate plus its Bernoulli sample noise.
  Intercept-resend drives this up linearly (intensity/4); PNS leaves it at
  zero; trojan creeps up slowly.
- **Decoy-loss family**: variance of the per-intensity loss rates and its
  significance vs binomial noise (PNS's exclusive tell).
- **Gap/timing family**: detection-gap statistics over the transmission
  order. Suppressive attacks (PNS) produce runs of missing detections,
  i.e. heavy right tails in gap lengths; noise/intercept do not.

Features are protocol-agnostic: they read BB84Result-style fields
(``sample_errors``, ``sample_indices``, ``sifted_alice`` …) present on both
BB84Result and B92Result.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: Feature names in output order; kept in sync with :func:`extract_features`.
FEATURE_NAMES: list[str] = [
    "qber",
    "sample_n",
    "qber_binomial_z",
    "sifted_fraction",
    "loss_rate",
    "loss_rate_z",
    "decoy_loss_var",
    "decoy_loss_z",
    "pns_flag",
    "gap_mean",
    "gap_p95",
    "gap_max",
    "gap_tail_ratio",
    "error_count",
    "error_nn_scaled",
    "qber_x_scatter",
]


def _gaps_from_outcomes(bob_outcomes: list[int] | None, n: int) -> list[int]:
    """Distances between consecutive detected pulses (PNS timing signature)."""
    if bob_outcomes is not None and len(bob_outcomes) > 0:
        detected = [i for i, o in enumerate(bob_outcomes) if o != -1]
    else:
        detected = list(range(n))  # no loss modelling: everything detected
    gaps = [b - a for a, b in zip(detected, detected[1:])]
    return gaps or [1]


def _decoy_loss_features(attack_stats: dict | None) -> dict[str, float]:
    """Variance and significance of per-intensity decoy loss rates."""
    if not attack_stats or not attack_stats.get("levels"):
        return {
            "decoy_loss_var": 0.0,
            "decoy_loss_z": 0.0,
        }
    rates = np.array([lvl["loss_rate"] for lvl in attack_stats["levels"]], float)
    sent = np.array([lvl["sent"] for lvl in attack_stats["levels"]], float)
    var = float(rates.var()) if rates.size else 0.0

    # Significance: variance of a homogeneous-loss null vs binomial noise.
    # E[var] under the null ~ p(1-p)/n summed across levels; z = observed/E.
    p_bar = float(sent @ rates / sent.sum()) if sent.sum() else 0.0
    expected_var = float(np.sum(p_bar * (1 - p_bar) / np.maximum(sent, 1)))
    z = var / expected_var if expected_var > 0 else 0.0
    return {"decoy_loss_var": var, "decoy_loss_z": z}


def _error_cluster_features(
    sample_indices: list[int], sample_alice: list[int], sample_bob: list[int], n_sifted: int
) -> dict[str, float]:
    """Spatial clustering of sample errors inside the sifted key.

    Trojan disturbance is *localized by construction* (leakage patches), so
    its errors bunch together; intercept-resend's wrong-basis events are
    scattered uniformly. Metric: mean nearest-neighbour gap between error
    positions, scaled by k/n (expected value ~1 under a uniform spread,
    <<1 for clustered errors, >>1 for repulsion — neutral 1.0 when fewer
    than two errors exist to measure).
    """
    errs = sorted(
        i for i, a, b in zip(sample_indices, sample_alice, sample_bob) if a != b
    )
    if len(errs) < 2:
        return {"error_nn_scaled": 1.0, "error_count": float(len(errs))}
    gaps = [b - a for a, b in zip(errs, errs[1:])]
    # Each interior point's NN is min(left, right) gap; ends see one gap.
    nn = [
        min(gaps[j - 1], gaps[j]) if 0 < j < len(gaps) else gaps[0 if j == 0 else -1]
        for j in range(len(errs))
    ]
    mean_nn = float(np.mean(nn))
    scaled = mean_nn * len(errs) / max(n_sifted, 1)
    return {
        "error_nn_scaled": float(scaled),
        "error_count": float(len(errs)),
    }


def extract_features(result: Any, n_sent: int | None = None) -> dict[str, float]:
    """Compute the feature dict for one simulation result.

    Parameters
    ----------
    result:
        A BB84Result / B92Result (or any object with the same field names).
    n_sent:
        Number of transmitted qubits; defaults to ``len(result.alice_bits)``.
    """
    n_sent = n_sent if n_sent is not None else len(result.alice_bits)
    n_sample = len(result.sample_indices)
    n_err = result.sample_errors

    # --- QBER family --------------------------------------------------------
    qber = result.qber or 0.0
    # How many sample-error SDs above an honest (0-QBER) channel? The QBER
    # estimate over n Bernoulli(p) trials has SD sqrt(p(1-p)/n); p=0.5 is
    # the conservative worst case.
    binom_sd = 0.5 / np.sqrt(max(n_sample, 1))
    qber_binomial_z = qber / binom_sd if binom_sd > 0 else 0.0

    # --- Decoy-loss family ----------------------------------------------------
    decoy = _decoy_loss_features(getattr(result, "attack_stats", None))
    pns_flag = 1.0 if (getattr(result, "attack_stats", None) or {}).get("flagged") else 0.0

    # Loss rate & significance: fraction of transmitted qubits Bob never
    # detected (sifted < transmitted implies losses). Binomial z against a
    # 0-loss channel separates "some loss" from "attacker-grade loss".
    sifted_n = len(result.sifted_alice)
    loss_rate = max(0.0, 1.0 - sifted_n / max(n_sent, 1))
    loss_sd = np.sqrt(max(n_sent, 1) * 0.01 * 0.99) / max(n_sent, 1)
    loss_rate_z = (loss_rate - 0.0) / loss_sd

    # --- Gap/timing family ----------------------------------------------------
    gaps = _gaps_from_outcomes(getattr(result, "bob_outcomes", None), n_sent)
    g = np.array(gaps, float)
    gap_mean = float(g.mean())
    gap_p95 = float(np.percentile(g, 95))
    gap_max = float(g.max())
    # Heavy-tail measure: how much of the total gap mass sits past the p95.
    gap_tail_ratio = float(g[g >= gap_p95].sum() / g.sum()) if g.sum() > 0 else 0.0

    cluster = _error_cluster_features(
        list(result.sample_indices),
        list(result.sample_alice),
        list(result.sample_bob),
        sifted_n,
    )

    return {
        "qber": qber,
        "sample_n": float(n_sample),
        "qber_binomial_z": float(qber_binomial_z),
        "sifted_fraction": sifted_n / max(n_sent, 1),
        "loss_rate": loss_rate,
        "loss_rate_z": float(loss_rate_z),
        **decoy,
        "pns_flag": pns_flag,
        "gap_mean": gap_mean,
        "gap_p95": gap_p95,
        "gap_max": gap_max,
        "gap_tail_ratio": gap_tail_ratio,
        **cluster,
        # Interaction prior: scattered attacks (nn~1) carry their full QBER
        # into this feature; clustered attacks (nn<1) get suppressed. Lets a
        # linear model separate intercept-resend from trojan at equal QBER.
        "qber_x_scatter": qber * cluster["error_nn_scaled"],
    }


def feature_vector(features: dict[str, float]) -> list[float]:
    """Feature dict -> fixed-order vector (must match FEATURE_NAMES)."""
    return [float(features[name]) for name in FEATURE_NAMES]
