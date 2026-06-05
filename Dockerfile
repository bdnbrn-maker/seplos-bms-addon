ARG BUILD_FROM
FROM $BUILD_FROM

# Installa dipendenze Python
RUN apk add --no-cache python3 py3-pip py3-serial && \
    pip3 install --no-cache-dir paho-mqtt

# Copia i file dell'add-on
WORKDIR /app
COPY run.py .

# Punto di ingresso
CMD ["python3", "/app/run.py"]
