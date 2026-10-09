FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /runner
COPY runner.py /runner/runner.py
USER 65534:65534
ENTRYPOINT ["python", "-I", "/runner/runner.py"]
