"""ML classification endpoint: identify the attack signature of a run.

POST /ml/classify — two modes:

- ``{"run_id": <id>}`` — classify a previously persisted SimulationRun by
  replaying its stored ``result_json`` through the feature extractor. No new
  simulation happens.
- ``{"protocol": "bb84"|"b92", "n_qubits": ..., "seed": ...,
  "attack_type": ..., "attack_intensity": ...}`` — run one fresh simulation
  server-side and classify it. Classification-only runs are deliberately
  *not* persisted: they are probes, not key-establishment history.

The model is the LogisticRegression pipeline trained by
``python -m app.ml.train`` (artifact: ``app/ml/attack_classifier.joblib``).
If the artifact is missing the endpoint answers 503 rather than pretending.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import joblib
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.attacks import make_hook
from app.ml.feature_extraction import extract_features, feature_vector
from app.models import SimulationRun, get_db
from app.routers.simulate import PROTOCOLS, RunIn, _validated

router = APIRouter(prefix="/ml", tags=["ml"])

DbDep = Annotated[Session, Depends(get_db)]

_MODEL_DIR = Path(__file__).resolve().parent.parent / "ml"
MODEL_PATH = _MODEL_DIR / "attack_classifier.joblib"
META_PATH = _MODEL_DIR / "attack_classifier_meta.json"


class ClassifyById(BaseModel):
    """Classify a persisted run."""

    run_id: int


class ClassifyFresh(BaseModel):
    """Run a fresh simulation and classify it."""

    protocol: str = "bb84"
    n_qubits: int = 2048
    seed: int | None = None
    attack_type: str | None = None
    attack_intensity: float = 0.0


class ClassificationOut(BaseModel):
    """Prediction + class probabilities + the features they came from."""

    predicted_class: str
    probabilities: dict[str, float]
    features: dict[str, float]
    run_id: int | None = None
    model_meta: dict[str, Any]


@lru_cache(maxsize=1)
def _load_model():
    """Load the trained pipeline once; None when the artifact is absent."""
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


@lru_cache(maxsize=1)
def _load_meta() -> dict:
    if META_PATH.exists():
        import json

        return json.loads(META_PATH.read_text())
    return {}


def _require_model():
    model = _load_model()
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "attack classifier not trained yet — run "
                "`python -m app.ml.train` to produce the model artifact"
            ),
        )
    return model


def _class_names() -> list[str]:
    """Human-readable class names aligned with model.classes_ order.

    The pipeline is fit on integer labels; the saved metadata carries the
    index -> name mapping (train.py's CLASSES).
    """
    names = _load_meta().get("classes")
    if not names:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="model metadata missing — retrain with `python -m app.ml.train`",
        )
    return list(names)


def _classify(result_like: Any) -> tuple[str, dict[str, float], dict[str, float]]:
    """Shared scoring path: features -> pipeline -> probabilities dict."""
    model = _require_model()
    features = extract_features(result_like)
    proba = model.predict_proba([feature_vector(features)])[0]
    names = _class_names()
    probabilities = {
        names[int(c)]: float(p) for c, p in zip(model.classes_, proba)
    }
    predicted = max(probabilities, key=probabilities.get)
    return predicted, probabilities, features


@router.post("/classify", response_model=ClassificationOut)
def classify(
    payload: ClassifyById | ClassifyFresh,
    db: DbDep,
    user: auth.CurrentUser,
) -> ClassificationOut:
    """Classify the attack signature behind one simulation result."""
    if isinstance(payload, ClassifyById):
        run = db.get(SimulationRun, payload.run_id)
        if run is None or run.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
            )
        # result_json round-trips lists/floats faithfully; the extractor only
        # reads attributes, so a lightweight namespace suffices.
        from types import SimpleNamespace

        result_like = SimpleNamespace(**run.result_json)
        predicted, probabilities, features = _classify(result_like)
        return ClassificationOut(
            predicted_class=predicted,
            probabilities=probabilities,
            features=features,
            run_id=run.id,
            model_meta=_load_meta(),
        )

    # Fresh-simulation mode: validate bounds, run the real pipeline, classify.
    if payload.protocol not in PROTOCOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown protocol '{payload.protocol}'",
        )
    req = _validated(
        RunIn(
            n_qubits=payload.n_qubits,
            seed=payload.seed,
            attack_type=payload.attack_type,
            attack_intensity=payload.attack_intensity,
        )
    )
    run_fn, _ = PROTOCOLS[payload.protocol]
    result = run_fn(
        n_qubits=req.n_qubits,
        seed=req.seed,
        channel_hook=make_hook(req.attack_type, req.attack_intensity),
        attack_type=req.attack_type,
        attack_intensity=req.attack_intensity,
    )
    predicted, probabilities, features = _classify(result)
    return ClassificationOut(
        predicted_class=predicted,
        probabilities=probabilities,
        features=features,
        model_meta=_load_meta(),
    )
