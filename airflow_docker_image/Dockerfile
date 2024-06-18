FROM apache/airflow:latest

USER root

# Устанавливаем OpenJDK 11 для PySpark
RUN apt-get update && apt-get install -y openjdk-11-jdk && \
    apt-get clean

RUN apt-get install -y wget

# Скачиваем сам Apache Spark
RUN wget -qO- https://archive.apache.org/dist/spark/spark-3.2.0/spark-3.2.0-bin-hadoop3.2.tgz | tar xvz -C /opt && \
    mv /opt/spark-3.2.0-bin-hadoop3.2 /opt/spark && \
    chown -R airflow: /opt/spark

# Устанавливаем PySpark
RUN pip install pyspark

# Копируем requirements.txt и устанавливаем зависимости
COPY requirements.txt /requirements.txt
RUN python -m pip install --upgrade pip && pip install --no-cache-dir -r /requirements.txt

USER airflow