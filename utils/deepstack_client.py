import os
from datetime import datetime, timezone

import requests
from requests import RequestException
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "gif", "webp"}
ALLOWED_MIME_PREFIX = "image/"


class DeepstackClientError(Exception):
    def __init__(self, message, status_code=502, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def validate_image_upload(uploaded_file):
    if uploaded_file is None:
        return None, "No file was uploaded."

    filename = secure_filename(uploaded_file.filename or "")
    if not filename:
        return None, "Please choose an image file first."

    if "." not in filename:
        return None, "Uploaded file has no extension."

    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed_text = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return None, f"Unsupported file type '{extension}'. Allowed: {allowed_text}."

    mimetype = uploaded_file.mimetype or ""
    if mimetype and not mimetype.startswith(ALLOWED_MIME_PREFIX):
        return None, f"Invalid file MIME type '{mimetype}'. Only images are supported."

    return uploaded_file, None


def _normalize_confidence(value):
    try:
        confidence_float = float(value)
    except (TypeError, ValueError):
        confidence_float = 0.0

    confidence_float = max(0.0, confidence_float)

    if confidence_float > 1.0:
        confidence_percent = min(confidence_float, 100.0)
        confidence_score = confidence_percent / 100.0
    else:
        confidence_score = confidence_float
        confidence_percent = confidence_float * 100.0

    return confidence_score, confidence_percent


def _confidence_profile(confidence_percent):
    if confidence_percent >= 80:
        return {
            "level": "high",
            "explanation": "Very strong match. The model is highly confident in this fruit label.",
            "bar_class": "success",
        }

    if confidence_percent >= 50:
        return {
            "level": "medium",
            "explanation": "Moderate confidence. The prediction is plausible but not definitive.",
            "bar_class": "warning",
        }

    return {
        "level": "low",
        "explanation": "Low confidence. The image may be unclear or outside model training patterns.",
        "bar_class": "danger",
    }


def _extract_predictions(payload):
    predictions = []

    if not isinstance(payload, dict):
        raise DeepstackClientError("DeepStack response format is invalid.", status_code=502)

    if payload.get("error"):
        raise DeepstackClientError(
            f"DeepStack reported an error: {payload['error']}",
            status_code=502,
            details={"response": payload},
        )

    if "label" in payload:
        score, percent = _normalize_confidence(payload.get("confidence"))
        predictions.append(
            {
                "label": str(payload.get("label", "Unknown")),
                "confidence": round(score, 4),
                "confidence_percent": round(percent, 2),
            }
        )

    if isinstance(payload.get("predictions"), list):
        for item in payload["predictions"]:
            if not isinstance(item, dict):
                continue

            score, percent = _normalize_confidence(item.get("confidence"))
            predictions.append(
                {
                    "label": str(item.get("label", "Unknown")),
                    "confidence": round(score, 4),
                    "confidence_percent": round(percent, 2),
                }
            )

    if not predictions:
        raise DeepstackClientError(
            "DeepStack returned no predictions for this image.",
            status_code=502,
            details={"response": payload},
        )

    predictions = sorted(
        predictions,
        key=lambda prediction: prediction.get("confidence_percent", 0),
        reverse=True,
    )

    return predictions


def call_custom_model(uploaded_file, base_url, model_name, timeout_seconds=45):
    clean_base_url = (base_url or "").rstrip("/")
    endpoint = f"{clean_base_url}/v1/vision/custom/{model_name}"

    filename = secure_filename(uploaded_file.filename or "") or "uploaded-image"
    mimetype = uploaded_file.mimetype or "application/octet-stream"
    uploaded_file.stream.seek(0)

    try:
        response = requests.post(
            endpoint,
            files={"image": (filename, uploaded_file.stream, mimetype)},
            timeout=timeout_seconds,
        )
    except RequestException as exc:
        raise DeepstackClientError(
            "Could not reach DeepStack service.",
            status_code=503,
            details={"endpoint": endpoint, "exception": str(exc)},
        ) from exc

    raw_preview = response.text[:500].replace("\n", " ").strip()

    if response.status_code == 404:
        raise DeepstackClientError(
            "DeepStack custom endpoint was not found.",
            status_code=404,
            details={
                "endpoint": endpoint,
                "response_preview": raw_preview,
                "hint": (
                    "Current DeepStack build may not expose /v1/vision/custom/<model> "
                    "for ONNX custom models."
                ),
            },
        )

    if response.status_code != 200:
        raise DeepstackClientError(
            f"DeepStack returned HTTP {response.status_code}.",
            status_code=response.status_code,
            details={"endpoint": endpoint, "response_preview": raw_preview},
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DeepstackClientError(
            "DeepStack returned a non-JSON response.",
            status_code=502,
            details={"endpoint": endpoint, "response_preview": raw_preview},
        ) from exc

    return {
        "endpoint": endpoint,
        "status_code": response.status_code,
        "payload": payload,
        "response_preview": raw_preview,
    }


def build_prediction_response(deepstack_payload, endpoint, model_name):
    predictions = _extract_predictions(deepstack_payload)
    top_prediction = predictions[0]
    profile = _confidence_profile(top_prediction["confidence_percent"])

    return {
        "model_name": model_name,
        "endpoint": endpoint,
        "fruit": top_prediction["label"],
        "confidence": top_prediction["confidence"],
        "confidence_percent": top_prediction["confidence_percent"],
        "confidence_level": profile["level"],
        "confidence_bar_class": profile["bar_class"],
        "confidence_explanation": profile["explanation"],
        "predictions": predictions[:5],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "deepstack_base_url": os.getenv("DEEPSTACK_BASE_URL", "http://localhost:5050"),
            "model_name": model_name,
        },
    }

