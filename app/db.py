import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path):
    with closing(connect(path)) as conn:
        conn.executescript(SCHEMA.read_text())


def read_df(path, sql, params=()):
    with closing(connect(path)) as conn:
        return pd.read_sql_query(sql, conn, params=list(params))
