import psycopg2


def get_connection():
    return psycopg2.connect(
        dbname="wcffbp",
        user="postgres",
        password="Bl@Rg2!!^99",
        host="localhost",
        port="5432",
    )