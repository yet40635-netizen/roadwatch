FROM roadwatch:local
USER root
RUN pip install --no-cache-dir -r requirements-ml.txt
USER roadwatch
CMD ["python", "-m", "uvicorn", "inference.main:app", "--host", "0.0.0.0", "--port", "8011"]
