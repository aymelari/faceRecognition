"""
face_service.py
───────────────
Pure-Python face recognition service.

Dependencies (add to requirements.txt):
    face_recognition==1.3.0   (wraps dlib)
    numpy>=1.24
    Pillow>=10.0

All heavy ML work is isolated here so views stay thin.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ── Confidence threshold ────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.80          # Below this → reject match
MAX_FACE_SAMPLES_PER_EMPLOYEE = 5    # Enroll limit per employee


@dataclass
class VerifyResult:
    matched: bool
    employee_id: Optional[int]
    employee_name: Optional[str]
    confidence: float
    reason: str = ""


# ── Lazy import so the module loads even without dlib in dev ────────────────
def _fr():
    try:
        import face_recognition as fr
        return fr
    except ImportError:
        raise ImportError(
            "face_recognition is not installed. "
            "Run: pip install face_recognition"
        )


# ── Public helpers ──────────────────────────────────────────────────────────

def extract_embedding(image_file) -> np.ndarray:
    """
    Given a Django InMemoryUploadedFile or file-like object,
    return a 128-d face embedding.

    Raises:
        ValueError – if no face or multiple faces detected.
    """
    fr = _fr()
    img = Image.open(image_file).convert("RGB")
    img_array = np.array(img)

    locations = fr.face_locations(img_array, model="hog")  # fast; use "cnn" on GPU

    if len(locations) == 0:
        raise ValueError("No face detected in the image.")
    if len(locations) > 1:
        raise ValueError(
            f"{len(locations)} faces detected. Please upload an image with exactly one face."
        )

    encodings = fr.face_encodings(img_array, known_face_locations=locations)
    if not encodings:
        raise ValueError("Could not extract face embedding.")

    return encodings[0].astype(np.float32)


def verify_face(image_file, employee_faces: list) -> VerifyResult:
    """
    Compare uploaded image against a list of (employee_id, name, embedding_bytes) tuples.

    Returns the best-matching VerifyResult.
    """
    try:
        query_embedding = extract_embedding(image_file)
    except ValueError as exc:
        return VerifyResult(matched=False, employee_id=None, employee_name=None,
                            confidence=0.0, reason=str(exc))

    if not employee_faces:
        return VerifyResult(matched=False, employee_id=None, employee_name=None,
                            confidence=0.0, reason="No enrolled faces in the system.")

    fr = _fr()
    best_confidence = 0.0
    best_employee_id = None
    best_employee_name = None

    # Group by employee so we average per-employee distances
    from collections import defaultdict
    employee_embeddings: dict[int, list[np.ndarray]] = defaultdict(list)
    employee_names: dict[int, str] = {}

    for emp_id, emp_name, emb_bytes in employee_faces:
        emb = np.frombuffer(bytes(emb_bytes), dtype=np.float32)
        employee_embeddings[emp_id].append(emb)
        employee_names[emp_id] = emp_name

    for emp_id, embeddings in employee_embeddings.items():
        # face_recognition uses Euclidean distance; lower = better match
        distances = fr.face_distance(embeddings, query_embedding)
        min_distance = float(np.min(distances))
        # Convert distance → confidence (1 - distance, clamped to [0, 1])
        confidence = max(0.0, min(1.0, 1.0 - min_distance))

        if confidence > best_confidence:
            best_confidence = confidence
            best_employee_id = emp_id
            best_employee_name = employee_names[emp_id]

    if best_confidence >= CONFIDENCE_THRESHOLD:
        return VerifyResult(
            matched=True,
            employee_id=best_employee_id,
            employee_name=best_employee_name,
            confidence=round(best_confidence, 4),
        )

    return VerifyResult(
        matched=False,
        employee_id=None,
        employee_name=None,
        confidence=round(best_confidence, 4),
        reason=f"Best confidence {best_confidence:.2f} is below threshold {CONFIDENCE_THRESHOLD}.",
    )