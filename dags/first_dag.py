from airflow import DAG
from airflow.sensors.filesystem import FileSensor
from airflow.operators.dummy import DummyOperator
from airflow.operators.python_operator import PythonOperator
from datetime import datetime, timedelta

# Импортируем функцию из созданного пакета
from etl_package.etl import load_data_to_postgres

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2023, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'file_sensor_dag',
    default_args=default_args,
    schedule_interval='*/3 * * * *',  # Каждую минуту
    catchup=False,
    concurrency=1,         # Ограничиваем количество параллельно выполняемых задач
    max_active_runs=1,     # Ограничиваем количество активных экземпляров DAG
) as dag:
    start = DummyOperator(task_id='start')

    file_sensor = FileSensor(
        task_id='file_sensor',
        filepath='/opt/airflow/host_directory/sleep.csv',
        fs_conn_id='fs_default',
        poke_interval=1,  # Интервал между проверками наличия файла
        timeout=5,  # Время ожидания (в секундах), после которого сенсор завершится, если файл не найден
        soft_fail=False,  # Установка параметра soft_fail на False, чтобы сенсор падал при неудаче
        mode='poke',  # Используем режим poke для сенсора
    )

    load_data_to_postgres = PythonOperator(
        task_id='load_data_to_postgres',
        python_callable=load_data_to_postgres
    )

    end = DummyOperator(task_id='end')

    start >> file_sensor >> load_data_to_postgres >> end