import csv
import io
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import build_artifacts
import langextract_style
import numpy as np
import pandas as pd
import pyodbc
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared_setup import build_lookups, load_label_csv, normalize_lineitem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_langextract_company")

app = FastAPI(title="LangExtract by Company Batch API")

# development origins — restrict this in production
origins = [
    "http://localhost:8008",  # Frontend port
    "http://127.0.0.1:8008",  # Frontend port alternative
    "http://localhost:8007",  # Backend port
    "http://127.0.0.1:8007",  # Backend port alternative
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST, OPTIONS, etc.
    allow_headers=["*"],  # allow custom headers (Authorization etc)
)

BASE_COMPANY_DIR = "company_data"
FALLBACK_CSV = "filtered_data.csv"
###########################
# SQL Processing Route
###########################

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler('gl_auto_comments.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Key Vault client
KEY_VAULT_NAME = os.getenv("KEY_VAULT_NAME")
KV_URI = f"https://{KEY_VAULT_NAME}.vault.azure.net/"

# Initialize Azure credentials
try:
    # In production, DefaultAzureCredential will automatically use the managed identity
    # configured in the deployment.yaml without needing explicit client ID
    credential = DefaultAzureCredential()
    logger.info("Successfully initialized DefaultAzureCredential")
    secret_client = SecretClient(vault_url=KV_URI, credential=credential)
except Exception as e:
    logger.error(f"Failed to initialize Azure credential: {str(e)}")
    raise

def get_secret(secret_name: str) -> str:
    """
    Fetch a secret from Azure Key Vault.
    
    Args:
        secret_name (str): Name of the secret in Key Vault
        
    Returns:
        str: Secret value
    """
    try:
        return secret_client.get_secret(secret_name).value
    except Exception as e:
        logger.error(f"Failed to fetch secret {secret_name} from Key Vault: {str(e)}")
        raise

def get_db_conn_str():
    """Get database connection string with credentials from Key Vault"""
    try:
        conn_str_secret = get_secret("DB-CONN-STR")
        parsed_conn_str = dict(item.split("=") for item in conn_str_secret.split(";") if "=" in item)
        
        # Construct connection string with database name from environment
        conn_str = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={parsed_conn_str.get('Data Source')};"
            f"DATABASE={os.getenv('DATABASE')};"  # Keep DATABASE from env vars
            f"UID={parsed_conn_str.get('User ID')};"
            f"PWD={parsed_conn_str.get('Password')};"
            "TrustServerCertificate=yes;"
        )
        return conn_str
    except Exception as e:
        logger.error(f"Failed to construct database connection string: {str(e)}")
        raise

# Initialize the connection string
CONN_STR = get_db_conn_str()


class CompanyRequest(BaseModel):
    company_code: str
    username: str


class StoreAutoMappingRequest(BaseModel):
    rows: list  # List of dicts, each with columns matching the final df


@app.post("/glmapapi/store_auto_mapping")
def store_auto_mapping(req: StoreAutoMappingRequest):
    # Insert each row into PL_Master_AutoMapping
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        for row in req.rows:
            CompanyCode = row.get("CompanyCode")
            GLCode = row.get("GLCode")
            LineItem = row.get("LineItem")
            GrandParent = row.get("GrandParent")
            Parent = row.get("Parent")
            UpdatedOn = row.get("UpdatedOn")
            # Get or generate UpdatedOn
            UpdatedOn = row.get("UpdatedOn")
            if not UpdatedOn:
                # Generate current timestamp in IST (UTC+5:30)
                UpdatedOn = datetime.utcnow() + timedelta(hours=5, minutes=30)
            else:
                # If UpdatedOn is provided, parse it to datetime
                try:
                    UpdatedOn = datetime.strptime(UpdatedOn, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    # If parsing fails, use current time
                    UpdatedOn = datetime.utcnow() + timedelta(hours=5, minutes=30)
            UpdatedBy = row.get("UpdatedBy")
            cursor.execute(
                """
                INSERT INTO PL_Master_AutoMapping (CompanyCode, GLCode, LineItem, GrandParent, Parent, UpdatedOn, UpdatedBy)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                CompanyCode,
                GLCode,
                LineItem,
                GrandParent,
                Parent,
                UpdatedOn,
                UpdatedBy,
            )
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "ok", "rows_inserted": len(req.rows)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to store auto mapping: {e}"
        )


def get_plmaster_mapping(company_code: str):
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    cursor.execute("EXEC Get_GetPLMaster_Mapping ?", company_code)

    columns = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    results = [dict(zip(columns, row)) for row in rows]

    cursor.close()
    conn.close()
    return results


def split_plmaster_mapping(df: pd.DataFrame):
    # Filter out rows where GLCode is null
    df = df[df["GLCode"].notna()]

    # 1) LineItems with no Parent & GrandParent but GLCode present
    LineItems_with_no_Parent_GrandParent = df[
        (df["Parent"].isna()) & (df["GrandParent"].isna())
    ]

    only_lineitems = LineItems_with_no_Parent_GrandParent["LineItem"].tolist()

    # 2) LineItems with both Parent & GrandParent and GLCode present
    LineItems_with_Parent_GrandParent = df[
        (df["Parent"].notna()) & (df["GrandParent"].notna())
    ]

    return (
        LineItems_with_no_Parent_GrandParent,
        LineItems_with_Parent_GrandParent,
        only_lineitems,
    )


def enrich_and_merge_predictions(
    no_pg_df: pd.DataFrame,
    with_pg_df: pd.DataFrame,
    predictions: list,
    company_code: str,
    username: str,
):
    """
    no_pg_df: DataFrame -> LineItems_with_no_Parent_GrandParent
    with_pg_df: DataFrame -> LineItems_with_Parent_GrandParent
    predictions: list of dicts (from /batch/langextract_by_company results)
    company_code: str
    usernameglmapapi
    """
    # 1) Convert predictions JSON to DataFrame, handle missing columns
    pred_df = pd.DataFrame(predictions)
    required_cols = ["line_item", "parent", "grandparent"]
    missing_cols = [col for col in required_cols if col not in pred_df.columns]
    if missing_cols:
        logger.error(
            f"Predictions missing columns: {missing_cols}. Actual columns: {list(pred_df.columns)}. Predictions: {predictions}"
        )
        # Create empty columns for missing ones
        for col in missing_cols:
            pred_df[col] = None
    # 2) Merge with no_pg_df (left join, so we keep all rows in no_pg_df)
    merged_df = no_pg_df.merge(
        pred_df[required_cols], left_on="LineItem", right_on="line_item", how="left"
    )
    # 3) Fill missing Parent/GrandParent in no_pg_df with prediction values
    merged_df["Parent"] = merged_df["Parent"].fillna(merged_df["parent"])
    merged_df["GrandParent"] = merged_df["GrandParent"].fillna(merged_df["grandparent"])
    # 4) Drop helper cols (line_item, parent, grandparent from prediction)
    merged_df = merged_df.drop(columns=["line_item", "parent", "grandparent"])
    # 5) Final combine with already-complete with_pg_df
    final_df = pd.concat([merged_df, with_pg_df], ignore_index=True)

    # Add new columns: Id, CompanyCode, UpdatedOn (IST), UpdatedBy
    # GLCode, LineItem, GrandParent, Parent must remain as is
    # Column order: Id, CompanyCode, GLCode, LineItem, GrandParent, Parent, UpdatedOn, UpdatedBy
    def get_ist_now():
        # IST is UTC+5:30
        return (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    final_df["Id"] = [str(uuid.uuid4()) for _ in range(len(final_df))]
    final_df["CompanyCode"] = company_code
    final_df["UpdatedOn"] = get_ist_now()
    final_df["UpdatedBy"] = username

    # Reorder columns
    # If any column is missing, add as empty string
    for col in ["GLCode", "LineItem", "GrandParent", "Parent"]:
        if col not in final_df.columns:
            final_df[col] = ""
    final_df = final_df[
        [
            "Id",
            "CompanyCode",
            "GLCode",
            "LineItem",
            "GrandParent",
            "Parent",
            "UpdatedOn",
            "UpdatedBy",
        ]
    ]
    return final_df


@app.post("/glmapapi/get_plmaster_mapping")
def get_plmaster_mapping_route(req: CompanyRequest):
    company_code = req.company_code.strip()
    username = req.username.strip()
    if not company_code:
        raise HTTPException(status_code=400, detail="company_code is required")

    try:
        data = get_plmaster_mapping(company_code)
        df = pd.DataFrame(data)

        # apply split
        df1, df2, only_lineitems = split_plmaster_mapping(df)

        # If there are lineitems missing parent/grandparent, get predictions
        predictions = []
        if only_lineitems:
            # Call batch/langextract_by_company internally
            batch_req = CompanyBatchRequest(
                company_code=company_code, lines=only_lineitems
            )
            batch_result = langextract_by_company(batch_req)
            predictions = batch_result.get("results", [])

        # Merge predictions with df1 and combine with df2, add extra columns
        final_df = enrich_and_merge_predictions(
            df1, df2, predictions, company_code, username
        )

        # Convert final_df to CSV for download
        csv_buffer = io.StringIO()
        final_df.to_csv(csv_buffer, index=False)
        csv_str = csv_buffer.getvalue()

        return {
            "company_code": company_code,
            "count_total": len(df),
            "count_df1": len(df1),
            "count_df2": len(df2),
            "LineItems_with_no_Parent_GrandParent": df1.to_dict(orient="records"),
            "LineItems_with_Parent_GrandParent": df2.to_dict(orient="records"),
            "only_lineitems": only_lineitems,
            "predictions": predictions,
            "final_csv": csv_str,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CompanyBatchRequest(BaseModel):
    company_code: str
    lines: List[str]


def _verify_artifacts_exist(artifacts_dir: str) -> bool:
    """Check if all required artifact files exist in the directory."""
    required_files = ["exact_lookup.json", "descriptions.json", "hierarchy.json"]
    for file in required_files:
        if not os.path.exists(os.path.join(artifacts_dir, file)):
            logger.warning(f"Missing required artifact file: {file} in {artifacts_dir}")
            return False
    return True


def _load_exact_lookup_from_artifacts(artifacts_dir: str):
    """Load exact_lookup.json from artifacts directory if all required files exist."""
    if not _verify_artifacts_exist(artifacts_dir):
        return None

    exact_path = os.path.join(artifacts_dir, "exact_lookup.json")
    try:
        with open(exact_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading exact_lookup.json from {artifacts_dir}: {str(e)}")
        return None


def _ensure_company_dirs(base_dir: str, company_code: str):
    code = company_code.strip() or "_default"
    company_root = os.path.join(base_dir, code)
    csv_dir = os.path.join(company_root, "csv")
    artifacts_dir = os.path.join(company_root, "artifacts")
    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(artifacts_dir, exist_ok=True)
    return code, csv_dir, artifacts_dir


# this is for local persistence of predictions
def _append_prediction_to_company_csv(
    csv_dir: str, company_code: str, line_item: str, parent: str, grandparent: str
):
    """
    Append a prediction to the company CSV if it doesn't already exist.
    If the line item exists with different parent/grandparent, updates the existing entry.
    """
    filename = f"{company_code}.csv"
    path = os.path.join(csv_dir, filename)
    header = ["LineItem", "Parent", "GrandParent"]

    # Normalize the inputs
    safe_line_item = (line_item or "").replace("\r", " ").replace("\n", " ").strip()
    safe_parent = (parent or "").replace("\r", " ").replace("\n", " ").strip()
    safe_grandparent = (grandparent or "").replace("\r", " ").replace("\n", " ").strip()

    # Read existing data if file exists
    existing_data = []
    file_exists = os.path.exists(path) and os.path.getsize(path) > 0

    if file_exists:
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != header:
                    # If headers don't match, we'll recreate the file
                    logger.warning(
                        f"CSV headers don't match expected format. Recreating {path}"
                    )
                else:
                    existing_data = list(reader)
        except Exception as e:
            logger.warning(f"Error reading existing CSV {path}: {e}")

    # Check if line item already exists
    item_exists = False
    for row in existing_data:
        if row["LineItem"].lower() == safe_line_item.lower():
            # Update existing entry if parent or grandparent has changed
            if row["Parent"] != safe_parent or row["GrandParent"] != safe_grandparent:
                row["Parent"] = safe_parent
                row["GrandParent"] = safe_grandparent
                logger.info(f"Updated existing entry for '{safe_line_item}'")
            item_exists = True
            break

    # If item doesn't exist, add it to the data
    if not item_exists:
        existing_data.append(
            {
                "LineItem": safe_line_item,
                "Parent": safe_parent,
                "GrandParent": safe_grandparent,
            }
        )
        logger.info(f"Added new entry for '{safe_line_item}'")

    # Write all data back to the file
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(existing_data)
    except Exception as e:
        logger.error(f"Failed to write to company CSV {path}: {e}")
        raise


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/glmapapi/batch/langextract_by_company")
def langextract_by_company(req: CompanyBatchRequest):
    # Validate input
    company_code = (req.company_code or "").strip()
    if not company_code:
        raise HTTPException(status_code=400, detail="company_code is required")
    if not req.lines or not any([l and l.strip() for l in req.lines]):
        raise HTTPException(
            status_code=400,
            detail="lines must contain at least one non-empty line item",
        )

    # Prepare company dirs (ensure for persistence)
    code, csv_dir, company_artifacts_dir = _ensure_company_dirs(
        BASE_COMPANY_DIR, company_code
    )
    global_artifacts_dir = "artifacts"  # Streamlit default global artifacts

    exact_lookup = {}
    examples = []
    parents = []
    grandparents = []

    # 1) Try company artifacts first
    company_artifacts_loaded = False
    logger.info(f"Checking for company artifacts in: {company_artifacts_dir}")
    if os.path.isdir(company_artifacts_dir):
        exact_lookup = _load_exact_lookup_from_artifacts(company_artifacts_dir)
        if (
            exact_lookup is not None
        ):  # Only if all required files exist and loaded successfully
            logger.info(f"Loaded {len(exact_lookup)} entries from company artifacts")
            examples = [
                {
                    "lineitem": k,
                    "parent": v.get("parent", ""),
                    "grandparent": v.get("grandparent", ""),
                }
                for k, v in exact_lookup.items()
            ]
            parents = list(
                {v.get("parent", "") for v in exact_lookup.values() if v.get("parent")}
            )
            grandparents = list(
                {
                    v.get("grandparent", "")
                    for v in exact_lookup.values()
                    if v.get("grandparent")
                }
            )
            company_artifacts_loaded = True

    # 2) If company artifacts are incomplete or missing, try global artifacts
    if not company_artifacts_loaded:
        logger.info(
            f"Company artifacts not available, checking global artifacts in: {global_artifacts_dir}"
        )
        exact_lookup = _load_exact_lookup_from_artifacts(global_artifacts_dir)
        if (
            exact_lookup is not None
        ):  # Only if all required files exist and loaded successfully
            logger.info(f"Loaded {len(exact_lookup)} entries from global artifacts")
            examples = [
                {
                    "lineitem": k,
                    "parent": v.get("parent", ""),
                    "grandparent": v.get("grandparent", ""),
                }
                for k, v in exact_lookup.items()
            ]
            parents = list(
                {v.get("parent", "") for v in exact_lookup.values() if v.get("parent")}
            )
            grandparents = list(
                {
                    v.get("grandparent", "")
                    for v in exact_lookup.values()
                    if v.get("grandparent")
                }
            )
        else:
            logger.error("Global artifacts are also incomplete or missing")

    # 3) If no artifacts found, return empty results
    if not exact_lookup:
        logger.warning(f"No artifacts found in company or global directories")
        return {
            "company_code": company_code,
            "count": 0,
            "results": [],
            "message": "No artifacts found in company or global directories",
        }

    # 4) Normalize exact_lookup keys using normalize_lineitem to match Streamlit
    normalized_exact = {}
    if exact_lookup:
        try:
            for k, v in (exact_lookup or {}).items():
                nk = normalize_lineitem(k)
                normalized_exact[nk] = v
        except Exception:
            normalized_exact = exact_lookup or {}
    else:
        normalized_exact = {}

    # 5) Process each input line (exact match first, then LangExtract)
    results = []
    for raw_line in req.lines:
        if not raw_line or not raw_line.strip():
            continue
        line = raw_line.strip()
        li_norm = normalize_lineitem(line)

        # exact lookup (highest priority)
        if normalized_exact and li_norm in normalized_exact:
            match = normalized_exact[li_norm]
            parent_val = match.get("parent", "")
            grand_val = match.get("grandparent", "")

            # Determine the source of the exact match
            source = "llm_prediction"  # default to LLM if we can't determine

            # Check if the match exists in company artifacts
            company_match = False
            if company_artifacts_dir and os.path.exists(company_artifacts_dir):
                company_exact = _load_exact_lookup_from_artifacts(company_artifacts_dir)
                if company_exact and li_norm in company_exact:
                    company_match = True

            if company_match:
                source = "company_artifacts"
            else:
                # If not in company artifacts, it must be from global artifacts
                source = "global_artifacts"

            res = {
                "line_item": line,
                "normalized": li_norm,
                "parent": parent_val,
                "grandparent": grand_val,
                "parent_confidence": 1.0,
                "grandparent_confidence": 1.0,
                "source": source,
            }

            # persist same as Streamlit
            try:
                _append_prediction_to_company_csv(
                    csv_dir,
                    code,
                    line_item=line,
                    parent=parent_val,
                    grandparent=grand_val,
                )
            except Exception:
                logger.exception("Failed to persist exact-match prediction")
            results.append(res)
            continue

        # LLM-based LangExtract prediction
        try:
            prediction = langextract_style.predict_langextract(
                lineitem=li_norm,
                exact_lookup=normalized_exact or {},
                examples=examples,
                parents=parents,
                grandparents=grandparents,
            )

            parent_val = prediction.get("parent", "")
            grand_val = prediction.get("grandparent", "")

            res = {
                "line_item": line,
                "normalized": li_norm,
                "parent": parent_val,
                "grandparent": grand_val,
                "parent_confidence": prediction.get("parent_confidence", 0.0),
                "grandparent_confidence": prediction.get("grandparent_confidence", 0.0),
                "rationale": prediction.get("rationale", ""),
                "mappings_used": prediction.get("mappings_used", None),
                "source": "llm_prediction",  # This is explicitly from LLM
            }

            # persist same as Streamlit
            try:
                _append_prediction_to_company_csv(
                    csv_dir,
                    code,
                    line_item=line,
                    parent=parent_val,
                    grandparent=grand_val,
                )
            except Exception:
                logger.exception("Failed to persist LLM prediction")

            results.append(res)
        except Exception as e:
            logger.exception("Error predicting for line '%s': %s", line, str(e))
            res = {
                "line_item": line,
                "normalized": li_norm,
                "parent": "",
                "grandparent": "",
                "parent_confidence": 0.0,
                "grandparent_confidence": 0.0,
                "error": str(e),
                "source": "error",
            }
            results.append(res)

    return {"company_code": company_code, "count": len(results), "results": results}


@app.post("/glmapapi/upload/extract_missing")
async def upload_extract_missing(file: UploadFile = File(...)):
    """
    Upload parser (only 'lineitem' required; case-insensitive).
    Optional columns: parent, grandparent, companycode.
    Returns:
      {
        company_code: str | null,
        missing_lineitems: [...],
        premapped_rows: [{line_item,parent,grandparent,row_index}, ...],
        partial_rows: [...],
        counts: {...}
      }
    """
    contents = await file.read()
    buf = io.BytesIO(contents)

    # 1) Read file (Excel or CSV). Try Excel for .xls/.xlsx else CSV.
    try:
        if file.filename and file.filename.lower().endswith((".xls", ".xlsx")):
            df = pd.read_excel(buf, engine="openpyxl", dtype=object)
        else:
            try:
                text = contents.decode("utf-8")
            except Exception:
                text = contents.decode("latin1")
            df = pd.read_csv(io.StringIO(text), dtype=object)
    except Exception:
        # fallback: try csv with header=None (we'll reject headerless if no lineitem)
        try:
            try:
                text = contents.decode("utf-8")
            except Exception:
                text = contents.decode("latin1")
            df = pd.read_csv(io.StringIO(text), header=None, dtype=object)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to parse uploaded file: {e}"
            )

    # drop rows/cols that are completely empty
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all").reset_index(drop=True)

    # must have rows
    if df.shape[0] == 0:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file contains no data after removing empty rows/columns.",
        )

    # normalize headers -> map lowercase header -> original header
    original_columns = list(df.columns)
    normalized_headers = {str(c).strip().lower(): c for c in original_columns}

    # required: only lineitem
    if "lineitem" not in normalized_headers:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Uploaded file must contain a 'lineitem' column (case-insensitive).",
                "found_columns": original_columns,
            },
        )

    # resolve optional columns if present
    line_col = normalized_headers["lineitem"]
    parent_col = normalized_headers.get("parent")  # may be None
    grand_col = normalized_headers.get("grandparent")  # may be None
    company_col = normalized_headers.get("companycode")  # may be None

    # replace NaN with empty and coerce to stripped strings; treat common null-like strings as empty
    df = df.replace({np.nan: ""})

    def clean_str(x):
        s = "" if x is None else str(x).strip()
        if s.lower() in {"nan", "null", "none"}:
            return ""
        return s

    # apply cleaning to line_col and any optional columns we care about
    df[line_col] = df[line_col].apply(clean_str)
    if parent_col:
        df[parent_col] = df[parent_col].apply(clean_str)
    if grand_col:
        df[grand_col] = df[grand_col].apply(clean_str)
    if company_col:
        df[company_col] = df[company_col].apply(clean_str)

    # ensure at least one non-empty lineitem exists
    non_empty_line_mask = df[line_col].astype(str).str.strip() != ""
    if not non_empty_line_mask.any():
        raise HTTPException(
            status_code=400, detail="No non-empty values found in lineitem column."
        )

    # COMPANY CODE: try company_col if present; else scan all columns for company-like values
    company_code = None
    if company_col:
        company_vals = df[company_col].astype(str).str.strip()
        company_vals = company_vals[company_vals != ""]
        if not company_vals.empty:
            company_code = company_vals.value_counts().idxmax()
    if not company_code:
        # scan all columns for company-like pattern e.g. C2360, A123 (letter followed by digits)
        company_pattern = re.compile(r"^[A-Za-z]\d{1,}$")
        candidates = []
        for col in df.columns:
            vals = df[col].astype(str).str.strip()
            vals = vals[vals != ""]
            if vals.empty:
                continue
            matches = vals[vals.str.match(company_pattern, na=False)]
            if not matches.empty:
                candidates.extend(matches.tolist())
        if candidates:
            # pick most common
            import collections

            company_code = collections.Counter(candidates).most_common(1)[0][0]

    # if still not found, company_code remains None (caller can decide how to handle)
    # Now classify rows: missing (both empty), premapped (both present), partial (one present)
    def is_missing_val(v: str) -> bool:
        return v is None or str(v).strip() == ""

    parent_missing = (
        df[parent_col].apply(is_missing_val)
        if parent_col
        else pd.Series([True] * len(df))
    )
    grand_missing = (
        df[grand_col].apply(is_missing_val)
        if grand_col
        else pd.Series([True] * len(df))
    )

    mask_missing_both = parent_missing & grand_missing
    mask_parent_and_grand_present = (~parent_missing) & (~grand_missing)
    mask_partial = (~mask_missing_both) & (~mask_parent_and_grand_present)

    # only include rows where lineitem exists
    mask_line_present = non_empty_line_mask

    missing_mask = mask_missing_both & mask_line_present
    premapped_mask = mask_parent_and_grand_present & mask_line_present
    partial_mask = mask_partial & mask_line_present

    # collect outputs
    missing_lineitems = df.loc[missing_mask, line_col].astype(str).str.strip().tolist()

    def row_obj(idx):
        return {
            "line_item": str(df.at[idx, line_col]).strip(),
            "parent": str(df.at[idx, parent_col]).strip() if parent_col else "",
            "grandparent": str(df.at[idx, grand_col]).strip() if grand_col else "",
            "row_index": int(idx),
        }

    premapped_rows = [row_obj(i) for i in df[premapped_mask].index]
    partial_rows = [row_obj(i) for i in df[partial_mask].index]

    counts = {
        "total": int(mask_line_present.sum()),
        "missing": int(len(missing_lineitems)),
        "premapped": int(len(premapped_rows)),
        "partial": int(len(partial_rows)),
    }

    return {
        "company_code": company_code,  # may be null if not found
        "missing_lineitems": missing_lineitems,
        "premapped_rows": premapped_rows,
        "partial_rows": partial_rows,
        "counts": counts,
    }


logger = logging.getLogger("api_save_build")


class SaveAndBuildRequest(BaseModel):
    company_code: str
    rows: List[dict]  # expected keys: line_item, parent, grandparent (strings)
    base_company_dir: Optional[str] = "company_data"
    csv_filename: Optional[str] = None  # defaults to "<company_code>.csv"


@app.post("/glmapapi/save")
def save_and_build(req: SaveAndBuildRequest):
    logger.info(f"Received save request: {req.dict()}")
    """
    Writes rows to company CSV and runs build_artifacts on that CSV.
    If CSV exists, it will be overwritten.
    """
    company_code = (req.company_code or "").strip()
    if not company_code:
        raise HTTPException(status_code=400, detail="company_code is required")

    base_dir = req.base_company_dir or "company_data"
    company_root = os.path.join(base_dir, company_code)
    csv_dir = os.path.join(company_root, "csv")
    artifacts_dir = os.path.join(company_root, "artifacts")

    # Create directories if they don't exist
    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(artifacts_dir, exist_ok=True)

    csv_name = req.csv_filename or f"{company_code}.csv"
    csv_path = os.path.join(csv_dir, csv_name)

    # Check if file exists to append or create new
    file_exists = os.path.exists(csv_path)
    existing_lines = set()

    # If file exists, read existing lines to avoid duplicates
    if file_exists:
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                existing_lines = {tuple(row) for row in reader}
        except Exception as e:
            logger.error(f"Error reading existing CSV: {e}")
            # Continue with empty set if can't read existing file

    # Write CSV (create new or append)
    try:
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["LineItem", "Parent", "GrandParent"])

            # Add existing lines
            for line in existing_lines:
                writer.writerow(line)

            # Add new lines, avoiding duplicates
            for r in req.rows:
                li = (
                    (r.get("line_item") or "")
                    .replace("\r", " ")
                    .replace("\n", " ")
                    .strip()
                )
                p = (
                    (r.get("parent") or "")
                    .replace("\r", " ")
                    .replace("\n", " ")
                    .strip()
                )
                g = (
                    (r.get("grandparent") or "")
                    .replace("\r", " ")
                    .replace("\n", " ")
                    .strip()
                )

                # Only add if not already in existing lines
                if (li, p, g) not in existing_lines:
                    writer.writerow([li, p, g])
                    existing_lines.add((li, p, g))
    except Exception as e:
        logger.exception("Failed writing csv")
        raise HTTPException(status_code=500, detail=f"Failed writing CSV: {e}")

    # Rebuild artifacts with the updated CSV
    try:
        build_artifacts.main(csv_path, artifacts_dir)
    except Exception as e:
        logger.exception("build_artifacts failed")
        raise HTTPException(
            status_code=500,
            detail=f"build_artifacts failed: {e}",
            headers={"csv_path": csv_path, "artifacts_dir": artifacts_dir},
        )

    return {
        "status": "ok",
        "csv_path": csv_path,
        "artifacts_dir": artifacts_dir,
        "rows_processed": len(req.rows),
        "total_rows": len(existing_lines),
    }
