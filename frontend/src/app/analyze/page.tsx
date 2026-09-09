"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import {
  ImageQualityIssue,
  ImageUploadResponse,
  UploadError,
  uploadImage,
} from "@/lib/api";
import { getOrCreateAppSession } from "@/lib/session";

const ISSUE_LABELS: Record<ImageQualityIssue, string> = {
  too_low_resolution: "Image resolution is too low.",
  too_blurry: "Image appears too blurry.",
  too_dark: "Image appears too dark.",
  overexposed: "Image appears overexposed (too bright).",
  extreme_shadows: "Image has extreme shadows.",
  low_contrast: "Image contrast is too low.",
  unsupported_format: "Image format is not supported.",
  unsupported_orientation: "Image orientation could not be processed.",
  insufficient_skin_visibility: "Not enough visible skin in the image.",
};

type Status = "idle" | "uploading" | "success" | "error";

export default function AnalyzePage() {
  const [status, setStatus] = useState<Status>("idle");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [result, setResult] = useState<ImageUploadResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelected(file: File) {
    setResult(null);
    setErrorMessage(null);
    setPreviewUrl(URL.createObjectURL(file));
    setStatus("idle");
  }

  async function handleUpload() {
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setStatus("uploading");
    setErrorMessage(null);
    try {
      const sessionId = await getOrCreateAppSession();
      const response = await uploadImage(file, sessionId);
      setResult(response);
      setStatus("success");
    } catch (err) {
      const message =
        err instanceof UploadError
          ? err.message
          : "Upload failed. Please try again.";
      setErrorMessage(message);
      setStatus("error");
    }
  }

  function handleRetry() {
    setStatus("idle");
    setResult(null);
    setErrorMessage(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Skin Check</h1>
      <p className="text-neutral-600 dark:text-neutral-300">
        Upload a clear, well-lit photo. Supported formats: JPEG, PNG.
      </p>

      <div className="rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm text-neutral-500 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
        Your photo is checked for image quality (blur, brightness, contrast,
        resolution) before anything else. Retention is configurable and
        minimal, and photos are never used for anything beyond this
        analysis.
      </div>

      <div className="flex flex-col gap-3">
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileSelected(file);
          }}
          className="text-sm"
        />

        {previewUrl && (
          // eslint-disable-next-line @next/next/no-img-element -- object URL preview, not a static asset
          <img
            src={previewUrl}
            alt="Selected upload preview"
            className="max-h-80 w-auto rounded-lg border border-neutral-200 object-contain dark:border-neutral-800"
          />
        )}

        {previewUrl && status !== "success" && (
          <button
            onClick={handleUpload}
            disabled={status === "uploading"}
            className="self-start rounded-full bg-neutral-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
          >
            {status === "uploading"
              ? "Checking image quality…"
              : "Upload & Check Quality"}
          </button>
        )}
      </div>

      {status === "error" && errorMessage && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
        >
          {errorMessage}
        </div>
      )}

      {status === "success" && result && (
        <div className="flex flex-col gap-4">
          <div
            className={`rounded-lg border px-4 py-3 text-sm ${
              result.quality.is_acceptable
                ? "border-green-300 bg-green-50 text-green-900 dark:border-green-900 dark:bg-green-950 dark:text-green-200"
                : "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
            }`}
          >
            <p className="font-medium">
              {result.quality.is_acceptable
                ? "Image quality looks good."
                : "Image quality is insufficient for reliable visual analysis."}
            </p>
            <p className="mt-1">
              Quality score: {(result.quality.score * 100).toFixed(0)}%
            </p>
            {result.quality.issues.length > 0 && (
              <ul className="mt-2 list-disc pl-5">
                {result.quality.issues.map((issue) => (
                  <li key={issue}>{ISSUE_LABELS[issue] ?? issue}</li>
                ))}
              </ul>
            )}
          </div>

          {result.quality.metrics && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-neutral-500 dark:text-neutral-400">
              <dt>Resolution</dt>
              <dd>
                {result.quality.metrics.width} &times;{" "}
                {result.quality.metrics.height}px
              </dd>
              <dt>Blur score</dt>
              <dd>{result.quality.metrics.blur_score.toFixed(1)}</dd>
              <dt>Brightness</dt>
              <dd>{result.quality.metrics.brightness_score.toFixed(1)}</dd>
              <dt>Contrast</dt>
              <dd>{result.quality.metrics.contrast_score.toFixed(1)}</dd>
            </dl>
          )}

          <div className="flex flex-wrap gap-3">
            {result.quality.is_acceptable && (
              <Link
                href={`/results/${result.analysis_id}`}
                className="rounded-full bg-neutral-900 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-neutral-700 dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                View Visual Observations
              </Link>
            )}
            <button
              onClick={handleRetry}
              className="rounded-full border border-neutral-300 px-6 py-3 text-sm font-medium transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-900"
            >
              {result.quality.is_acceptable
                ? "Upload a different photo"
                : "Try another photo"}
            </button>
          </div>
        </div>
      )}

      <Disclaimer className="mt-auto" />
    </main>
  );
}
