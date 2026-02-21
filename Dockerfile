FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY app.py /app/app.py
COPY config.json /app/config.json
COPY Fruits.onnx /app/Fruits.onnx
COPY static /app/static
COPY templates /app/templates
COPY utils /app/utils

EXPOSE 81

CMD ["gunicorn", "--workers", "2", "--threads", "2", "--timeout", "120", "--bind", "0.0.0.0:81", "app:app"]
