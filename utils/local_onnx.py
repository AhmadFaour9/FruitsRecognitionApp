import json
import os
from functools import lru_cache

import numpy as np
import onnxruntime as ort
from PIL import Image


class LocalModelError(Exception):
    pass


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=4)
def _load_session(model_path):
    ort.set_default_logger_severity(3)

    if not os.path.exists(model_path):
        raise LocalModelError(f"Local ONNX model file not found: {model_path}")

    return ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])


def _load_config(config_path):
    if not os.path.exists(config_path):
        raise LocalModelError(f"Local model config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    return config


def _softmax(logits):
    logits = np.asarray(logits, dtype=np.float32)
    shifted = logits - np.max(logits)
    exp_values = np.exp(shifted)
    denominator = np.sum(exp_values)
    if denominator <= 0:
        return np.zeros_like(logits, dtype=np.float32)
    return exp_values / denominator


def predict_with_local_onnx(
    uploaded_file,
    model_path="Fruits.onnx",
    config_path="config.json",
):
    config = _load_config(config_path)
    session = _load_session(model_path)

    width = int(config.get("width", 224))
    height = int(config.get("height", 224))
    mean = _safe_float(config.get("mean", 0.5), 0.5)
    std = _safe_float(config.get("std", 255), 255.0)
    if std == 0:
        std = 255.0

    label_map = config.get("map", {})

    try:
        uploaded_file.stream.seek(0)
        image = Image.open(uploaded_file.stream).convert("RGB")
        image = image.resize((width, height))
    except Exception as exc:
        raise LocalModelError(f"Could not read image for local ONNX inference: {exc}") from exc

    image_array = np.asarray(image, dtype=np.float32)

    # Heuristic normalization for exported classification models.
    # For this model/config (mean=0.5, std=255), better results are obtained
    # using [-1, 1] style normalization: (x/255 - 0.5) / 0.5.
    if std >= 10 and 0.0 < mean < 1.0:
        normalized = (image_array / std - mean) / max(mean, 1e-6)
    else:
        normalized = (image_array - mean) / std

    input_tensor = normalized.transpose(2, 0, 1)[None, :, :, :]

    input_name = session.get_inputs()[0].name

    try:
        output_values = session.run(None, {input_name: input_tensor})[0]
    except Exception as exc:
        raise LocalModelError(f"Local ONNX inference failed: {exc}") from exc

    probabilities = _softmax(output_values.reshape(-1))

    predictions = []
    for class_index, probability in enumerate(probabilities):
        label = label_map.get(str(class_index), f"class_{class_index}")
        predictions.append(
            {
                "label": str(label),
                "confidence": float(probability),
            }
        )

    predictions = sorted(predictions, key=lambda item: item["confidence"], reverse=True)
    return predictions
