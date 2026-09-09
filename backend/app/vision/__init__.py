"""Computer vision pipeline (image quality + visual observations).

``quality.py`` (Phase 2) implements the non-diagnostic image quality gate.
``preprocessing.py``, ``region.py``, ``redness.py``, ``texture.py``,
``shine.py``, ``tone.py``, ``spots.py``, and ``analyzer.py`` (Phase 3)
implement the non-diagnostic visual-observation pipeline. See
``app.schemas.image.ImageQualityResult`` and
``app.schemas.vision.VisualObservation`` / ``VisualAnalysisResult`` for the
output contracts this package must satisfy.
"""
