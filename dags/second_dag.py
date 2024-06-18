from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.dummy import DummyOperator
from datetime import datetime

from etl_package.etl import extract_data_from_postgres, transform_data, load_data_into_clickhouse

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2024, 6, 1),
    'retries': 1,
}

cases = ['day_of_day', 'week_metrics']  # Список витрин для использования в задачах

with DAG(
    'postgres_to_clickhouse',
    default_args=default_args,
    schedule_interval='*/2 * * * *',
    catchup=False,
    concurrency=1,         # Ограничиваем количество параллельно выполняемых задач
    max_active_runs=1
) as dag:

    start = DummyOperator(task_id='start')

    extract = PythonOperator(
        task_id='extract_data_from_postgres',
        python_callable=extract_data_from_postgres
    )

    transform_tasks, load_tasks = [], []
    df = extract_data_from_postgres()
    transform_data = []

    for case in cases:
        transform_task = PythonOperator(
            task_id=f'transform_data_{case}',
            python_callable=transform_data,
            op_args=[],
            op_kwargs={'case': case,
                       'df': df},  # Передаем конкретный случай для трансформации
        )
        transform_tasks.append(transform_task)
        transform_tasks.append(transform_data)

        load_task = PythonOperator(
            task_id=f'load_data_into_clickhouse_{case}',
            python_callable=load_data_into_clickhouse,
            op_args=[],
            op_kwargs={'case': case},  # Передаем конкретный случай для загрузки
        )
        load_tasks.append(load_task)

    end = DummyOperator(task_id='end')

    start >> >> transform_tasks[0] >> load_tasks[0] >> end
    start >> transform_tasks[1] >> load_tasks[1] >> end