import os

import pandas as pd
import pyodbc
from dotenv import load_dotenv

load_dotenv()


class PLMasterRepository:
    def __init__(self):
        self.server = os.getenv("SERVER")
        self.database = os.getenv("DATABASE")
        self.username = "DEV_TANISH"
        self.password = os.getenv("PASSWORD")

        self.conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.server};DATABASE={self.database};"
            f"UID={self.username};PWD={self.password};TrustServerCertificate=yes;"
        )

    def get_plmaster_mapping(self, company_code: str):
        """Fetch stored procedure results for a given company_code"""
        try:
            conn = pyodbc.connect(self.conn_str)
            cursor = conn.cursor()

            cursor.execute("EXEC Get_GetPLMaster_Mapping ?", company_code)

            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

            results = [dict(zip(columns, row)) for row in rows]

            cursor.close()
            conn.close()

            return results
        except Exception as e:
            return {"error": str(e)}

    def split_plmaster_mapping(self, df: pd.DataFrame):
        """Split into (no parent/grandparent), (with parent+grandparent), and only lineitems"""
        df = df[df["GLCode"].notna()]  # ignore rows where GLCode is NULL

        # 1) No Parent & No GrandParent
        LineItems_with_no_Parent_GrandParent = df[
            (df["GrandParent"].isna()) & (df["Parent"].isna())
        ]
        only_lineitems = LineItems_with_no_Parent_GrandParent["LineItem"].tolist()

        # 2) With Parent & GrandParent
        LineItems_with_Parent_GrandParent = df[
            (df["GrandParent"].notna()) & (df["Parent"].notna())
        ]

        return (
            LineItems_with_no_Parent_GrandParent,
            LineItems_with_Parent_GrandParent,
            only_lineitems,
        )
