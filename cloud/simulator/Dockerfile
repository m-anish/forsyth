FROM python:3.12-slim
RUN pip install --no-cache-dir httpx pillow
WORKDIR /sim
COPY weather.py sim.py skycam.py ./
CMD ["python", "sim.py"]
