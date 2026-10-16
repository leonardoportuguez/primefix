import os
import psycopg
from psycopg.rows import dict_row


def get_connection():
    """Retorna uma conexão com o PostgreSQL usando a DATABASE_URL do ambiente."""
    database_url = os.environ.get("DATABASE_URL")
    conn = psycopg.connect(database_url, row_factory=dict_row)
    return conn


def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """Executa uma query SQL e retorna os resultados conforme solicitado."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())

        result = None
        if fetchone:
            result = cur.fetchone()
        elif fetchall:
            result = cur.fetchall()

        if commit:
            conn.commit()

        cur.close()
        return result
    finally:
        conn.close()