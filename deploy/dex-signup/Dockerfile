FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir grpcio-tools==1.76.0 bcrypt==4.3.0 fastapi==0.137.0 uvicorn==0.49.0
COPY create.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. create.proto
COPY server.py .
USER 65534
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5559", "--no-access-log"]
