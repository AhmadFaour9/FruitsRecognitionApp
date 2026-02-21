import logging
import os

from flask import Flask, jsonify, render_template, request

from utils.deepstack_client import (
    DeepstackClientError,
    build_prediction_response,
    call_custom_model,
    validate_image_upload,
)
from utils.local_onnx import LocalModelError, predict_with_local_onnx


app = Flask(__name__)

app.config["DEEPSTACK_BASE_URL"] = os.getenv("DEEPSTACK_BASE_URL", "http://localhost:5050").rstrip("/")
app.config["DEEPSTACK_MODEL_NAME"] = os.getenv("DEEPSTACK_MODEL_NAME", "FruitsRecognition")
app.config["DEEPSTACK_TIMEOUT_SECONDS"] = int(os.getenv("DEEPSTACK_TIMEOUT_SECONDS", "45"))
app.config["MAX_UPLOAD_MB"] = int(os.getenv("MAX_UPLOAD_MB", "10"))
app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_UPLOAD_MB"] * 1024 * 1024
app.config["PORT"] = int(os.getenv("PORT", "81"))
app.config["ENABLE_LOCAL_ONNX_FALLBACK"] = (
    os.getenv("ENABLE_LOCAL_ONNX_FALLBACK", "true").lower() in {"1", "true", "yes", "on"}
)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@app.get("/")
def index():
    return render_template(
        "index.html",
        deepstack_base_url=app.config["DEEPSTACK_BASE_URL"],
        model_name=app.config["DEEPSTACK_MODEL_NAME"],
        max_upload_mb=app.config["MAX_UPLOAD_MB"],
        allowed_extensions=["jpg", "jpeg", "png", "bmp", "gif", "webp"],
    )


@app.get("/api/health")
def health():
    return jsonify(
        {
            "success": True,
            "service": "fruits-recognition-app",
            "deepstack_base_url": app.config["DEEPSTACK_BASE_URL"],
            "model_name": app.config["DEEPSTACK_MODEL_NAME"],
            "local_onnx_fallback_enabled": app.config["ENABLE_LOCAL_ONNX_FALLBACK"],
        }
    )


@app.post("/api/predict")
def predict():
    uploaded_file, validation_error = validate_image_upload(request.files.get("file"))
    if validation_error:
        return jsonify({"success": False, "error": validation_error}), 400

    try:
        deepstack_result = call_custom_model(
            uploaded_file,
            base_url=app.config["DEEPSTACK_BASE_URL"],
            model_name=app.config["DEEPSTACK_MODEL_NAME"],
            timeout_seconds=app.config["DEEPSTACK_TIMEOUT_SECONDS"],
        )

        app.logger.info(
            "DeepStack response status=%s endpoint=%s preview=%s",
            deepstack_result["status_code"],
            deepstack_result["endpoint"],
            deepstack_result["response_preview"],
        )

        data = build_prediction_response(
            deepstack_result["payload"],
            endpoint=deepstack_result["endpoint"],
            model_name=app.config["DEEPSTACK_MODEL_NAME"],
        )
        return jsonify({"success": True, "data": data}), 200

    except DeepstackClientError as exc:
        if exc.status_code == 404 and app.config["ENABLE_LOCAL_ONNX_FALLBACK"]:
            try:
                local_predictions = predict_with_local_onnx(uploaded_file)
                local_payload = {"predictions": local_predictions}
                data = build_prediction_response(
                    local_payload,
                    endpoint="local://onnx/Fruits.onnx",
                    model_name=app.config["DEEPSTACK_MODEL_NAME"],
                )
                return (
                    jsonify(
                        {
                            "success": True,
                            "fallback": True,
                            "warning": (
                                "DeepStack custom endpoint was not found. "
                                "Used local ONNX fallback model."
                            ),
                            "data": data,
                        }
                    ),
                    200,
                )
            except LocalModelError as local_exc:
                app.logger.error("Local ONNX fallback failed: %s", str(local_exc))

        app.logger.error("DeepStack error: %s | details=%s", str(exc), exc.details)
        return jsonify({"success": False, "error": str(exc), "details": exc.details}), exc.status_code
    except Exception as exc:
        app.logger.exception("Unexpected prediction error")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Unexpected server error while processing the prediction.",
                    "details": str(exc),
                }
            ),
            500,
        )


@app.post("/submit")
def submit_compat():
    # Backward compatibility route. Frontend should use /api/predict.
    return predict()


if __name__ == "__main__":
    app.run(debug=True, port=app.config["PORT"])
