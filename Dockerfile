# Nutzen Sie ein schlankes Python-Basisimage
FROM python:3.11-slim

# Installieren Sie grundlegende Systemabhängigkeiten (z.B. für pdfplumber, Netzwerktools oder Compiler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Setzen Sie das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopieren Sie zuerst die requirements.txt, um den Docker-Build-Cache optimal zu nutzen
COPY requirements.txt .

# Installieren Sie die Python-Abhängigkeiten
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install --with-deps chromium

# Kopieren Sie den gesamten restlichen Projektordner in den Container
COPY . .

# Exponieren Sie die Ports für Streamlit (8501) und MLflow (8050)
EXPOSE 8501
EXPOSE 8050

# Setzen Sie Python-Umgebungsvariablen für sauberes Logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Starten Sie den Bootstrapper, der MLflow und Streamlit koordiniert
CMD ["python", "main.py"]