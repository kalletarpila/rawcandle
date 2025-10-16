import sqlite3
import pandas as pd
from pathlib import Path

def get_unique_tickers_from_db(db_path=None):
    """Palauttaa listan uniikeista osakkeista tietokannasta (osakedata-taulu)."""
    if db_path is None:
        data_dir = Path(__file__).parent.parent / "data"
        db_path = data_dir / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query("SELECT DISTINCT osake FROM osakedata", conn)
    return df["osake"].tolist()

def get_data_for_ticker(ticker, db_path=None):
    """Palauttaa DataFramen yhdelle osakkeelle tietokannasta."""
    if db_path is None:
        data_dir = Path(__file__).parent.parent / "data"
        db_path = data_dir / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT pvm, open, high, low, close, volume FROM osakedata WHERE osake = ? ORDER BY pvm ASC",
            conn,
            params=(ticker,)
        )
    df = df.rename(columns={k: k.lower() for k in df.columns})
    return df

def get_all_tickers_data(db_path=None):
    """Palauttaa dictin: {ticker: DataFrame} kaikille osakkeille tietokannasta."""
    tickers = get_unique_tickers_from_db(db_path)
    return {ticker: get_data_for_ticker(ticker, db_path) for ticker in tickers}
