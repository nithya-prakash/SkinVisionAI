# Computer Vision Pipeline

**Status: Phase 2 (image quality gate) and Phase 3 (visual-observation
pipeline) implemented.**

## Non-diagnostic by design

The vision pipeline reports **visible or technical characteristics**,
never medical conditions. It must never output something like "you have
acne" or "this image confirms rosacea." Every output validates against
[`app.schemas.vision.VisualObservation`](../backend/app/schemas/vision.py),
which only allows a fixed, non-diagnostic feature vocabulary:

- `redness`
- `dryness`
- `visible_texture`
- `shine_oiliness`
- `uneven_tone`
- `visible_spots_marks`

Each observation carries a coarse `level` (`minimal` / `mild` / `moderate` /
`pronounced`), a feature-specific `score` in `[0, 1]`, a `confidence` in
`[0, 1]`, and a `method` string identifying the algorithm — a heuristic
estimate, not a clinical measurement or calibrated probability.

## Pipeline

```
Image -> Image Quality Gate (Phase 2) -> Preprocessing -> Region Selection
       -> Per-Feature Extraction -> Structured Observations -> Pydantic
       Validation -> Database Persistence
```

### 1. Image quality gate (Phase 2)

Before any visual analysis, `app.vision.quality.analyze_image_quality`
checks the image with OpenCV/Pillow. Every check is a generic,
non-diagnostic image-processing measurement:

| Check | Method | Configurable threshold (env var) | Default |
|---|---|---|---|
| Resolution | `width`/`height` from the decoded image | `IMAGE_MIN_WIDTH_PX` / `IMAGE_MIN_HEIGHT_PX` | 400 × 400 px |
| Blur | Variance of the Laplacian (`cv2.Laplacian(...).var()`) of the grayscale image — a standard focus measure; low variance means few sharp edges | `IMAGE_BLUR_VARIANCE_THRESHOLD` | 80.0 |
| Brightness (too dark) | Mean grayscale pixel intensity | `IMAGE_BRIGHTNESS_MIN` | 40.0 (0-255 scale) |
| Brightness (overexposed) | Mean grayscale pixel intensity | `IMAGE_BRIGHTNESS_MAX` | 215.0 (0-255 scale) |
| Contrast | Standard deviation of grayscale pixel intensity | `IMAGE_CONTRAST_MIN_STD` | 15.0 |

All five thresholds are centralized as `Settings` fields (`app/config.py`)
and consumed via `QualityThresholds.from_settings()`.

**Gate outcome.** `is_acceptable` is `False` if *any* check fails; `issues`
names each failing check. A rejected image is **not** an HTTP error at
upload time — the upload still succeeds (`POST /api/analysis/upload`
returns 201) so the frontend can show the specific reasons and let the
user retry. Phase 3 (below) enforces the gate on its own end: it refuses
to run on an image that never passed.

### 2. Preprocessing (Phase 3, `app/vision/preprocessing.py`)

Shared by the quality gate and the feature pipeline, deterministic, and
never destructive of the original uploaded file (it only ever operates on
an in-memory copy):

- **EXIF orientation correction** (`normalize_orientation`) — reused from
  Phase 2 rather than duplicated, so both stages agree on "which way is up."
- **Resize** (`resize_for_analysis`) — downscales (never upscales) so the
  longest edge is at most `VISION_MAX_ANALYSIS_DIMENSION` (default 1024px).
  Pure performance/determinism knob; does not affect the Phase 2 quality
  gate, which measures the full-resolution image.
- **Color-space conversion** (`to_bgr_array`) — PIL RGB to OpenCV BGR.
- **Denoising is deliberately *not* applied here.** A global blur/denoise
  step would directly suppress the texture and redness signals the
  pipeline is trying to measure. (One feature extractor, spots/marks,
  applies its own local, scoped denoising for a different, documented
  reason — see below.)

### 3. Region-of-interest selection (Phase 3, `app/vision/region.py`)

Feature extraction runs on a selected region, not the whole frame:

- **Face detection**: OpenCV's bundled Haar-cascade frontal-face detector
  (`haarcascade_frontalface_default.xml`, shipped inside
  `opencv-python-headless` itself — no download, no large pretrained
  model). This is a classical Viola-Jones detector, a *localization* step
  only: it returns a bounding box and nothing else. No facial identity,
  embedding, landmark data, or recognition of any kind is computed or
  stored — this cannot and does not identify a person.
- **Multiple faces**: only the largest detected face is analyzed; the
  count of all detections is reported so a "N faces were detected; only
  the largest was analyzed" limitation can be surfaced.
- **Margin expansion**: the detected box is expanded by
  `VISION_FACE_MARGIN_FRACTION` (default 25%) on each side, so the region
  includes forehead/cheeks/chin, then clipped to the image bounds.
- **Fallback**: if no face is detected, detection is unreliable (a
  false-positive-sized box below `VISION_FACE_MIN_SIZE_FRACTION` of the
  image's shorter side, default 15%), or the expanded box would still be
  smaller than a usable minimum (40px), the pipeline falls back to a
  deterministic centered square crop covering `VISION_CENTER_CROP_FRACTION`
  (default 60%) of the image's shorter side. This is never treated as an
  error -- a "no face detected" or "partial/poorly-framed" photo still
  gets a result, with the fallback disclosed in `limitations` and
  `region_used`.

### 4. Per-feature extraction (Phase 3)

Each feature lives in its own module (`redness.py`, `texture.py`,
`shine.py`, `tone.py`, `spots.py`), independently unit-tested, and returns
a raw `score` (0-1) plus the `method` that produced it. `analyzer.py`
wraps each into a `VisualObservation` with a shared `level` bucketing and
`confidence` value.

| Feature | Method | What it measures | Score meaning |
|---|---|---|---|
| `redness` | `lab_a_channel_mean` | Mean of the Lab color space's a* channel (green-red axis) across the region | 0 = neutral/no red bias, 1 = at or above `VISION_REDNESS_NORM_MAX` (default 12.0) mean a* |
| `visible_texture` | `laplacian_variance` | Variance of the Laplacian of the grayscale region — the same focus measure as the Phase 2 blur check, here interpreted as "amount of fine local detail" on an already-in-focus image | 0 = perfectly flat, 1 = at or above `VISION_TEXTURE_NORM_MAX` (default 600.0) |
| `shine_oiliness` | `hsv_specular_highlight_fraction` | Fraction of pixels that are both very bright (`VISION_SHINE_BRIGHTNESS_MIN`, default V≥220) and low-saturation (`VISION_SHINE_SATURATION_MAX`, default S≤60) — the signature of a specular highlight | A natural 0-1 fraction, no separate normalization |
| `uneven_tone` | `lab_l_channel_stddev_smoothed` | Standard deviation of a *Gaussian-smoothed* copy of the Lab L* (lightness) channel across the region | 0 = perfectly even, 1 = at or above `VISION_TONE_NORM_MAX` (default 18.0) |
| `visible_spots_marks` | `highpass_blob_count` | Connected components in a high-pass (difference from a heavily blurred baseline) map of a lightly denoised region, filtered to a plausible size range | 0 = no marks, 1 = at or above `VISION_SPOTS_NORM_MAX_COUNT` (default 25) marks |

Each feature's raw score is bucketed into `level` via three configurable
cut points (`..._mild_min`, `..._moderate_min`, `..._pronounced_min`) --
below `mild_min` is `minimal`. All thresholds live in `app/config.py`
(`Settings`), never as inline magic numbers in the analysis modules.

**Why uneven tone is smoothed before measuring (a real bug found during
testing):** an early version measured L* std-dev directly on the region.
Testing against a synthetic high-frequency-noise image showed this
incorrectly scored "pronounced" uneven tone on what was really just fine
texture noise -- the two measurements were conflated. Smoothing the L*
channel first (removing pixel-scale noise while preserving genuine
regional brightness differences, like a cheek being visibly brighter than
a forehead) fixed this; verified by rerunning the same test image, which
then correctly showed low texture-driven tone variation while still
correctly flagging a real, large-scale brightness gradient in a separate
test case.

**Why spots/marks denoises locally (also found during testing):** an
early version, tested against a synthetic image with realistic
photographic-level noise, spuriously counted **4,534** noise pixels as
"marks" on a completely blank frame. A small median-blur pre-filter
(`_DENOISE_KERNEL = 5`), applied only inside this one feature's
computation, fixed it -- the same test image then correctly reported zero
marks. This is the only place in the pipeline denoising is used, and only
because blob-counting is uniquely sensitive to pixel-level noise in a way
the other features aren't. **Residual limitation**: at extremely high,
uniform noise levels (denser than typical camera sensor noise -- e.g. the
project's own synthetic "high-frequency texture" test fixture, not a
realistic photo), some spurious mark detection still occurs; this is
disclosed rather than hidden, and further tightening was not pursued
further to avoid overfitting the detector to synthetic test images at the
expense of real photos.

### Apparent dryness: not estimated

No defensible, non-speculative image-only heuristic for skin hydration
exists. Rather than inventing a score, `dryness` is **never included** in
`observations` -- it is omitted entirely, and a fixed limitation is always
added instead: *"Apparent dryness is not reliably estimated from a
standard photo and is not included in this analysis."*

### Fairness limitation: redness is not skin-tone-corrected

Testing surfaced an important, disclosed limitation: the Lab a* channel
mean measures absolute warmth in the image, not redness *relative to a
person's own baseline skin tone*. It is not tone-corrected. A naturally
warmer-toned face can register a nonzero baseline redness score with no
visible irritation at all -- this is stated directly in
`redness.py`'s module docstring, in every redness observation's `note`
field, and here. A tone-corrected measurement (e.g. comparing a region
against that same photo's own detected baseline rather than an absolute
color-space value) would be a reasonable Phase 4+ improvement but was not
attempted in Phase 3, to avoid a larger, unvalidated redesign.

## Confidence: heuristic, not a calibrated probability

```
confidence = clip(quality_score * region_factor, 0.1, 1.0)
region_factor = 0.9 if a face was detected, else 0.65
```

`quality_score` is the same Phase 2 image-quality score already computed
for this image. The result is floored at 0.1 so a low-quality analysis is
never reported as literally zero-confidence, and it is documented
everywhere as a heuristic reliability estimate -- never phrased as "N%
probability of X." See `app.vision.features.compute_confidence`.

## Scoring: feature signal, never a health score

Per-feature `score` values represent *that specific visual signal only*.
This system never combines them into an overall "skin health score" or
any single number implying a beauty or health rating -- there is no such
field anywhere in the schema, and `VisualAnalysisResult` uses
`extra="forbid"` so one cannot be silently added later either.

## CLIP/ViT: optional, supplementary only — never required, never diagnostic

Per explicit project requirement, CLIP (or any pretrained vision-language
model) is **not** a required dependency in Phase 2, Phase 3, or later, and
is never responsible for diagnosing, classifying, or implying a medical
condition. Phase 3 uses only classical OpenCV/NumPy/Pillow techniques.

If added as a future experiment, CLIP would only ever contribute a
secondary, clearly-labeled confidence signal layered on top of, never in
place of, the OpenCV heuristic result. A generic pretrained vision encoder
is not a clinically validated skin-condition classifier, and this project
never represents it as one.

## Image ingestion and validation (Phase 2)

`POST /api/analysis/upload` (`app/api/analysis.py`) is a thin HTTP layer
over `app.services.image_service.ingest_image`, which composes:

```
API route -> image_service -> upload_validation -> vision.quality -> Pydantic result -> DB persistence
```

- **`app.core.upload_validation`** — never trusts the client. The claimed
  `Content-Type` is checked against an allow-list (JPEG/PNG only), then
  the actual bytes are decoded and verified with Pillow (catching a file
  that merely *claims* to be an image), and the *real* decoded format is
  re-checked against the same allow-list. Oversized or empty uploads are
  rejected before decoding. The client-supplied filename is sanitized to a
  safe basename (defeating `../` path traversal and NUL-byte tricks) and
  used only as display metadata — a UUID-based name is always generated
  for on-disk storage, so the client filename never touches a filesystem
  path.
- **Decompression-bomb guard (Phase 10)** — a small file whose *declared*
  header dimensions imply an enormous decoded pixel count (Pillow's
  `Image.MAX_IMAGE_PIXELS` check, evaluated as soon as the header is
  read, before any expensive per-pixel work) is rejected with a
  controlled `400` (`image_too_large_decoded`), not an unhandled 500.
  See [docs/safety.md](safety.md#upload-safety).
- Errors map to HTTP status: `400` invalid/corrupted image content or
  oversized decoded dimensions, `415` unsupported format, `413` oversized
  upload, `422` missing file.

## Visual analysis endpoint (Phase 3)

`POST /api/analysis/{analysis_id}/visual-analysis`
(`app/api/analysis.py`) is a thin HTTP layer over
`app.services.vision_service.analyze_visual_features`, which composes:

```
API route -> vision_service -> (reuses Phase 2's persisted quality result)
-> app.vision.analyzer -> Pydantic result -> DB persistence
```

It **reuses** Phase 2's already-computed, already-persisted quality
result rather than re-running or duplicating quality analysis. Structured
errors, never a fabricated result:

| Status | Code | When |
|---|---|---|
| 404 | `analysis_not_found` | Unknown `analysis_id` |
| 404 | `image_not_found` | The linked image row is missing (shouldn't normally happen) |
| 422 | `quality_gate_not_passed` | The image never passed the Phase 2 quality gate |
| 409 | `image_not_retained` | Uploaded with `IMAGE_RETENTION_MODE=none`; nothing on disk to analyze |
| 404 | `image_file_missing` | The stored file is unexpectedly gone or unreadable |

On success, the result is persisted onto the existing `SkinAnalysis` row
(`visual_observations` and `structured_response` JSON columns from Phase
1 — no new migration was needed) and `status` is set to `completed`. The
endpoint is idempotent-by-design: because every algorithm is
deterministic, calling it again for the same `analysis_id` re-computes
and returns byte-for-byte identical `score`/`level` values (verified in
tests and manually against the live API).

## Image privacy and retention (Phase 2)

Controlled by `IMAGE_RETENTION_MODE`:

- **`temporary`** (default) — the image is written to `UPLOAD_DIRECTORY`
  under a server-generated filename, so Phase 3 can retrieve it later.
- **`none`** — the image is analyzed entirely in memory (`io.BytesIO`) and
  **never written to disk**; the database's `storage_path` column is left
  `null`, and Phase 3's visual-analysis endpoint correctly refuses to run
  against it (`image_not_retained`, 409) rather than pretending the image
  is still available.

In both modes: raw image bytes are never logged, never stored in the
database (only metadata and JSON results are), and never included in
error responses.

`temporary`-mode files are expired automatically by a background job
after `IMAGE_RETENTION_TTL_HOURS` (default 24h) — see
[docs/safety.md](safety.md#upload-safety) for how the cleanup runs.

## Output contract

```json
{
  "analysis_id": "b2a0ddef-b788-47b7-8d19-ee57dd13e014",
  "image_id": "c6be0d16-854a-416f-9452-20827a9c07c2",
  "observations": [
    {
      "feature": "redness",
      "level": "pronounced",
      "score": 1.0,
      "confidence": 0.65,
      "method": "lab_a_channel_mean",
      "note": "Estimated from color analysis, not tone-corrected; lighting, white balance, and a person's baseline skin tone all affect this measurement."
    }
  ],
  "region_used": "center_crop_fallback",
  "limitations": [
    "These are visual estimates that can be affected by lighting, camera quality, image resolution, makeup, filters, and shadows.",
    "Apparent dryness is not reliably estimated from a standard photo and is not included in this analysis."
  ],
  "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice.",
  "created_at": "2026-09-08T11:28:32.282651Z"
}
```

(Real output from a live run against a synthetic red-tinted test image —
not a fabricated example.)

## Limitations

- All metrics are technical heuristics, not medical measurements, and are
  affected by lighting, camera quality, makeup, filters, shadows, image
  resolution, and skin coverage.
- Redness is not corrected for a person's baseline skin tone (see above).
- Region-of-interest selection uses a classical face detector that can
  fail on non-frontal, partial, poorly lit, or unusual framing — the
  center-crop fallback is a reasonable default, not a guarantee the
  analyzed region contains skin at all.
- The spots/marks detector remains somewhat sensitive to very dense,
  uniform, high-frequency noise (see above).
- **Testing limitation**: this pipeline's test suite uses only synthetic,
  procedurally generated images (uniform colors, tinted regions, per-pixel
  noise, planted shapes) to verify algorithm correctness, deterministic
  behavior, schema validity, and pipeline wiring. It does **not** and
  cannot demonstrate real-world skin-analysis accuracy, and no such claim
  is made anywhere in this project.
