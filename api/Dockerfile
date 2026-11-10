# Image de l'API Digital Social Score (même image pour tous les modèles)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1. Dépendances d'abord (couche mise en cache tant que requirements.txt ne change pas).
#    --extra-index-url : version CPU de torch (~200 Mo au lieu de ~2 Go pour la version GPU)
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# 2. Code + modèle (model/ contient les poids et meta.json, ou est vide -> modèle factice)
COPY main.py preprocessing.py scorer.py ./
COPY model/ ./model/

# Cache Hugging Face DANS l'image (checkpoint LAYA pré-téléchargé par export_model.py),
# lu hors ligne : aucun téléchargement au démarrage des pods
ENV HF_HOME=/app/model/hf_cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# 3. Utilisateur non-root (bonne pratique sécurité)
RUN useradd --create-home --uid 1000 appuser
USER 1000

# Port d'écoute configurable (8080 par défaut)
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-access-log"]