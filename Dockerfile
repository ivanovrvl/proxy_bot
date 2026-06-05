FROM python:3.12-alpine
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chmod=0755 olcrtc-linux-amd64 .
COPY *.py .
CMD ["python", "main.py"]
