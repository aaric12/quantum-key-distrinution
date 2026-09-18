"""Train an attack classifier on synthetic labeled BB84/B92 runs.

Pipeline:
1. Generate N labeled synthetic runs with the *real* Step-7 machinery:
   ``run_bb84``/``run_b92`` under each attack hook (intercept_resend, pns,
   trojan) across a range of intensities, plus honest runs (none / 0.0).
2. Extract feature vectors (``app.ml.feature_extraction``).
3. Train a multinomial LogisticRegression on a standardized pipeline;
   hold out a stratified test split.
4. Report accuracy and one-vs-rest ROC AUC on the held-out split — printed
   here, never hardcoded anywhere.
5. Save the fitted pipeline + metadata for ``POST /ml/classify``.

Usage:  python -m app.ml.train [--runs-per-class 40] [--seed 7]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.feature_extraction import FEATURE_NAMES, extract_features, feature_vector
from app.protocols.b92 import run_b92
from app.protocols.bb84 import run_bb84

# Class order is fixed and saved with the model: index i of predict_proba's
# columns corresponds to CLASSES[i].
CLASSES: list[str] = ["none", "intercept_resend", "pns", "trojan"]

# Intensity grid per attack: low values are the hard cases (a 0.1
# intercept-resend looks nearly honest — that's where the classifier earns
# its keep).
ATTACK_GRID: dict[str, list[float]] = {
    "intercept_resend": [0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0],
    "pns": [0.1, 0.25, 0.5, 0.75, 1.0],
    "trojan": [0.1, 0.25, 0.5, 0.75, 1.0],
}

N_QUBITS = 4096  # per synthetic run; big enough for stable QBER estimates

MODEL_PATH = Path(__file__).resolve().parent / "attack_classifier.joblib"
META_PATH = Path(__file__).resolve().parent / "attack_classifier_meta.json"


def synthesize_runs(runs_per_class: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Generate labeled feature vectors using the real protocol + attack code."""
    X: list[list[float]] = []
    y: list[int] = []
    run_no = 0

    def add(result, label: int) -> None:
        nonlocal run_no
        feats = extract_features(result)
        X.append(feature_vector(feats))
        y.append(label)
        run_no += 1

    for ci, attack in enumerate(CLASSES):
        # Deterministic-but-varied seeds: reproducible dataset, not
        # degenerate (every run differs in its sampled qubits).
        for k in range(runs_per_class):
            run_seed = seed * 1_000_003 + run_no
            run_fn = run_bb84 if run_no % 2 == 0 else run_b92
            if attack == "none":
                result = run_fn(n_qubits=N_QUBITS, seed=run_seed)
            else:
                # Spread each run across the intensity grid round-robin.
                intensity = ATTACK_GRID[attack][k % len(ATTACK_GRID[attack])]
                result = _run_with_attack(run_fn, attack, intensity, run_seed)
            add(result, ci)

    return np.array(X, float), np.array(y, int)


def _run_with_attack(run_fn, attack: str, intensity: float, run_seed: int):
    """One attacked run through the real channel-hook plumbing."""
    from app.attacks import make_hook  # local import avoids a cycle at load

    return run_fn(
        n_qubits=N_QUBITS,
        seed=run_seed,
        channel_hook=make_hook(attack, intensity),
        attack_type=attack,
        attack_intensity=intensity,
    )


def train(runs_per_class: int, seed: int) -> dict:
    """Build the dataset, fit, evaluate on a holdout, and save the artifact."""
    X, y = synthesize_runs(runs_per_class, seed)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=seed
    )

    clf = Pipeline(
        steps=[
            ("scaler", StandardScaler()),                (
                    "logreg",
                    LogisticRegression(max_iter=5000, C=2.0),
                ),
        ]
    )
    clf.fit(X_train, y_train)

    # --- held-out evaluation: the numbers that get printed -----------------
    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)
    accuracy = float(accuracy_score(y_test, y_pred))

    # One-vs-rest AUC needs probability columns; guard tiny/degenerate splits.
    try:
        auc = float(
            roc_auc_score(y_test, y_prob, multi_class="ovr", average="macro")
        )
    except ValueError:
        auc = float("nan")

    print(f"dataset: {X.shape[0]} runs, {X.shape[1]} features, "
          f"train={len(y_train)} test={len(y_test)} (stratified holdout)")
    print(f"held-out accuracy: {accuracy:.3f}")
    print(f"held-out ROC AUC (macro OvR): {auc:.3f}")

    # Per-class recall on the holdout — small enough to print in full.
    per_class = {}
    for ci, name in enumerate(CLASSES):
        mask = y_test == ci
        if mask.sum():
            recall = float((y_pred[mask] == ci).mean())
            per_class[name] = recall
            print(f"  recall[{name:>16}]: {recall:.3f}  (n={int(mask.sum())})")

    # --- persist ------------------------------------------------------------
    joblib.dump(clf, MODEL_PATH)
    meta = {
        "classes": CLASSES,
        "feature_names": FEATURE_NAMES,
        "n_qubits": N_QUBITS,
        "runs_per_class": runs_per_class,
        "seed": seed,
        "heldout_accuracy": accuracy,
        "heldout_auc": auc,
        "per_class_recall": per_class,
        "sklearn": __import__("sklearn").__version__,
    }
    META_PATH.write_text(json.dumps(meta, indent=2))
    print(f"model saved: {MODEL_PATH}")
    print(f"meta saved:  {META_PATH}")
    return meta


if __name__ == "__main__":
    # Training-time only: sklearn/scipy emit solver chatter (deprecated
    # multi_class kwarg, lbfgs iprint) that drowns the metrics output.
    import warnings

    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-per-class", type=int, default=120)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    train(args.runs_per_class, args.seed)
