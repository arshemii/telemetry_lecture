FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcu_simulator.py .
CMD ["python", "-u", "mcu_simulator.py"]
