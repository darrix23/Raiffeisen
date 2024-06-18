import pandas as pd
import psycopg2
import re
from clickhouse_driver import Client
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

def load_data_to_postgres():
    df = pd.read_csv(r'/opt/airflow/host_directory/sleep.csv')

    conn = psycopg2.connect(
        dbname='airflow',
        user='airflow',
        password='airflow',
        host='postgres',
        port='5432'
    )
    cur = conn.cursor()

    data_pattern = r'(\d{1,2})\.(\d{1,2})\.(\d{4})'

    for row in df.itertuples():
        match = re.match(data_pattern, row._1)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            date_str = f'{year}-{month:02d}-{day:02d}'
            date = datetime.strptime(date_str, '%Y-%m-%d').date()

            cur.execute("""
                INSERT INTO sleep.raw_sleep (date, up, down)
                VALUES (%s, %s, %s)
                ON CONFLICT (date) 
                DO UPDATE SET
                    up = EXCLUDED.up,
                    down = EXCLUDED.down
                WHERE sleep.raw_sleep.date = EXCLUDED.date
            """, (date, row._2, row._3))

    conn.commit()
    cur.close()
    conn.close()

def extract_data_from_postgres():

    conn = psycopg2.connect(
        dbname="airflow",
        user="airflow",
        password="airflow",
        host="postgres",
        port="5432"
    )
    query = ('''SELECT up, down, date
                  FROM sleep.raw_sleep
                 ORDER BY date''')
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def transform_data(df, case):

    spark = SparkSession.builder \
        .appName("Raiffeisen") \
        .getOrCreate()

    # Преобразуем pandas DataFrame в Spark DataFrame
    spark_df = spark.createDataFrame(df)

    if case == 'day_of_day':
        # Преобразуем столбцы 'date', 'up' и 'down' к типу datetime
        spark_df = spark_df.withColumn('up', F.to_timestamp(F.concat(F.col('date'), F.lit(' '), F.col('up')),
                                                            'yyyy-MM-dd HH:mm:ss')) \
            .withColumn('down',
                        F.to_timestamp(F.concat(F.col('date'), F.lit(' '), F.col('down')), 'yyyy-MM-dd HH:mm:ss'))

        # Добавляем столбец 'next_day_up' с временем up на следующий день
        spark_df = spark_df.withColumn('next_day_up', F.date_add('date', 1) + F.expr('INTERVAL 24 HOURS'))

        # Добавляем столбец 'duration' с продолжительностью сна
        spark_df = spark_df.withColumn('duration',
                                       F.when(F.isnull('next_day_up') | F.isnull('down'), F.lit('1970-01-01 00:00:00')) \
                                       .otherwise(F.col('next_day_up') - F.col('down')))

        # Вычисляем плавающее среднее для столбца 'down'
        window_down = Window.orderBy('date').rowsBetween(-3, 3)
        spark_df = spark_df.withColumn('float_down', F.avg('down').over(window_down))

        # Вычисляем плавающее среднее для столбца 'up'
        window_up = Window.orderBy('date').rowsBetween(-3, 3)
        spark_df = spark_df.withColumn('float_up', F.avg('up').over(window_up))

        # Вычисляем плавающее среднее для столбца 'duration' на основе рассчитанных продолжительностей сна
        window_duration = Window.orderBy('date').rowsBetween(-3, 3)
        spark_df = spark_df.withColumn('float_duration', F.avg('duration').over(window_duration))

        # Выбираем нужные столбцы для результата
        result = spark_df.select('date', 'up', 'down', 'duration', 'float_down', 'float_up', 'float_duration').toPandas()

    elif case == 'week_metrics':
        # Добавляем столбец 'DAY_of_week' с номером дня недели (от 1 до 7)
        spark_df = spark_df.withColumn('DAY_of_week', F.dayofweek(F.to_date('date', 'yyyy-MM-dd')))

        # Создаем две строки из одной для каждой метрики: 'up' и 'down'
        up_df = spark_df.withColumn('type_of_metric', F.lit('up')).withColumn('value_of_metric', 'up')
        down_df = spark_df.withColumn('type_of_metric', F.lit('down')).withColumn('value_of_metric', 'down')

        # Объединяем два DataFrame в один
        result = up_df.union(down_df).toPandas()

    return result

def load_data_into_clickhouse(df):

    client = Client(
        host='clickhouse',
        user='airflow',
        password='airflow'
    )

    if case == 'day_of_day':
        # Truncate таблицы daily_metrics
        client.execute('TRUNCATE TABLE sleep_data.daily_metrics')

        # Преобразование pandas DataFrame в список кортежей
        data_tuples = [tuple(x) for x in df.to_records(index=False)]

        # Загрузка данных в таблицу daily_metrics
        client.execute('INSERT INTO sleep_data.daily_metrics VALUES', data_tuples)

    elif case == 'week_metrics':

        client.execute('TRUNCATE TABLE sleep_data.split_week')
        # Подготовка данных для вставки
        data_tuples = [tuple(x) for x in df.to_records(index=False)]

        # Вставка данных в таблицу sleep_data.split_week
        client.execute('INSERT INTO sleep_data.split_week VALUES', data_tuples)

