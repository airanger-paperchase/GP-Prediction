# api_langextract_company.py
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import json
import csv
import logging
import io
import numpy as np
import re
from fastapi import UploadFile, File
import pandas as pd
from fastapi.middleware.cors import CORSMiddleware
from shared_setup import load_label_csv, build_lookups, normalize_lineitem
import langextract_style
import build_artifacts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_langextract_company")

app = FastAPI(title="LangExtract by Company Batch API")

# development origins — restrict this in production
origins = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:8000",  # if you also use CRA
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # or ["*"] for quick local testing
    allow_credentials=True,
    allow_methods=["*"],        # GET, POST, OPTIONS, etc.
    allow_headers=["*"],        # allow custom headers (Authorization etc)
)

BASE_COMPANY_DIR = "company_data"
FALLBACK_CSV = "filtered_data.csv"


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


def _append_prediction_to_company_csv(csv_dir: str, company_code: str, line_item: str, parent: str, grandparent: str):
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
            with open(path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != header:
                    # If headers don't match, we'll recreate the file
                    logger.warning(f"CSV headers don't match expected format. Recreating {path}")
                else:
                    existing_data = list(reader)
        except Exception as e:
            logger.warning(f"Error reading existing CSV {path}: {e}")
    
    # Check if line item already exists
    item_exists = False
    for row in existing_data:
        if row['LineItem'].lower() == safe_line_item.lower():
            # Update existing entry if parent or grandparent has changed
            if row['Parent'] != safe_parent or row['GrandParent'] != safe_grandparent:
                row['Parent'] = safe_parent
                row['GrandParent'] = safe_grandparent
                logger.info(f"Updated existing entry for '{safe_line_item}'")
            item_exists = True
            break
    
    # If item doesn't exist, add it to the data
    if not item_exists:
        existing_data.append({
            'LineItem': safe_line_item,
            'Parent': safe_parent,
            'GrandParent': safe_grandparent
        })
        logger.info(f"Added new entry for '{safe_line_item}'")
    
    # Write all data back to the file
    try:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(existing_data)
    except Exception as e:
        logger.error(f"Failed to write to company CSV {path}: {e}")
        raise

@app.get("/health")
def health():
    return {"status": "ok"}


# @app.post("/batch/langextract_by_company")
# def langextract_by_company(req: CompanyBatchRequest):
#     # Validate input
#     company_code = (req.company_code or "").strip()
#     if not company_code:
#         raise HTTPException(status_code=400, detail="company_code is required")

#     if not req.lines or not any([l.strip() for l in req.lines]):
#         raise HTTPException(status_code=400, detail="lines must contain at least one non-empty line item")

#     # Build company paths
#     company_root = os.path.join(BASE_COMPANY_DIR, company_code)
#     company_csv_dir = os.path.join(company_root, "csv")
#     company_artifacts_dir = os.path.join(company_root, "artifacts")

#     # 1) First try to find CSV in company-specific directory
#     csv_path = None
#     if os.path.isdir(company_csv_dir):
#         for name in os.listdir(company_csv_dir):
#             if name.lower().endswith(".csv"):
#                 csv_path = os.path.join(company_csv_dir, name)
#                 logger.info(f"Found company CSV: {csv_path}")
#                 break

#     # 2) If no company CSV, try loading default artifacts
#     if not csv_path:
#         default_artifacts_dir = os.path.join(BASE_COMPANY_DIR, "_default", "artifacts")
#         if os.path.exists(default_artifacts_dir):
#             exact_lookup = _load_exact_lookup_from_artifacts(default_artifacts_dir) or {}
#             logger.info(f"Using default artifacts from: {default_artifacts_dir}")
#             examples = []
#             parents = []
#             grandparents = []
            
#             # If we have default artifacts, use them
#             if exact_lookup:
#                 examples = [
#                     {"lineitem": k, "parent": v.get("parent", ""), "grandparent": v.get("grandparent", "")}
#                     for k, v in exact_lookup.items()
#                 ]
#                 parents = list({v.get("parent", "") for v in exact_lookup.values() if v.get("parent")})
#                 grandparents = list({v.get("grandparent", "") for v in exact_lookup.values() if v.get("grandparent")})
#         else:
#             exact_lookup = {}
#             examples = []
#             parents = []
#             grandparents = []
#     else:
#         # 3) If we have a company CSV, load it
#         try:
#             df = load_label_csv(csv_path)
#             exact_lookup, examples, parents, grandparents = build_lookups(df)
#             logger.info(f"Loaded {len(exact_lookup)} entries from company CSV")
#         except Exception as e:
#             logger.exception("Failed loading company CSV, falling back to defaults")
#             exact_lookup = {}
#             examples = []
#             parents = []
#             grandparents = []
    
#     # 4) Final fallback to default CSV if no data loaded yet
#     if not exact_lookup:
#         default_csv_path = os.path.join(BASE_COMPANY_DIR, "_default", "csv", "filtered_data.csv")
#         if os.path.exists(default_csv_path):
#             try:
#                 df = load_label_csv(default_csv_path)
#                 exact_lookup, examples, parents, grandparents = build_lookups(df)
#                 logger.info(f"Loaded {len(exact_lookup)} entries from default CSV")
#             except Exception as e:
#                 logger.exception("Failed loading default CSV")
#                 if not exact_lookup:
#                     exact_lookup = {}
    
#     if not exact_lookup:
#         logger.warning("No data loaded from any source - starting with empty lookup")

#     # Process each line item
#     results = []
#     for line in req.lines:
#         if not line or not line.strip():
#             continue
            
#         line = line.strip()
#         normalized = line.lower()
        
#         # 1) Check for exact match first (highest priority)
#         if exact_lookup and normalized in exact_lookup:
#             match = exact_lookup[normalized]
#             results.append({
#                 "line_item": line,
#                 "normalized": normalized,
#                 "parent": match.get("parent", ""),
#                 "grandparent": match.get("grandparent", ""),
#                 "parent_confidence": 1.0,
#                 "grandparent_confidence": 1.0,
#                 "source": "exact_match"
#             })
#             continue
            
#         # 2) If no exact match, try LLM prediction
#         try:
#             prediction = langextract_style.predict_langextract(
#                 lineitem=normalized,
#                 exact_lookup=exact_lookup or {},
#                 examples=examples,
#                 parents=parents,
#                 grandparents=grandparents,
#             )
#             results.append({
#                 "line_item": line,
#                 "normalized": normalized,
#                 "parent": prediction.get("parent", ""),
#                 "grandparent": prediction.get("grandparent", ""),
#                 "parent_confidence": prediction.get("parent_confidence", 0.0),
#                 "grandparent_confidence": prediction.get("grandparent_confidence", 0.0),
#                 "rationale": prediction.get("rationale", ""),
#                 "source": "llm_prediction"
#             })
#         except Exception as e:
#             logger.error(f"Error predicting for line '{line}': {str(e)}")
#             results.append({
#                 "line_item": line,
#                 "normalized": normalized,
#                 "parent": "",
#                 "grandparent": "",
#                 "parent_confidence": 0.0,
#                 "grandparent_confidence": 0.0,
#                 "error": str(e),
#                 "source": "error"
#             })
    
#     return {"company_code": company_code, "count": len(results), "results": results}

@app.post("/batch/langextract_by_company")
def langextract_by_company(req: CompanyBatchRequest):
    # Validate input
    company_code = (req.company_code or "").strip()
    if not company_code:
        raise HTTPException(status_code=400, detail="company_code is required")
    if not req.lines or not any([l and l.strip() for l in req.lines]):
        raise HTTPException(status_code=400, detail="lines must contain at least one non-empty line item")

    # Prepare company dirs (ensure for persistence)
    code, csv_dir, company_artifacts_dir = _ensure_company_dirs(BASE_COMPANY_DIR, company_code)
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
        if exact_lookup is not None:  # Only if all required files exist and loaded successfully
            logger.info(f"Loaded {len(exact_lookup)} entries from company artifacts")
            examples = [
                {"lineitem": k, "parent": v.get("parent", ""), "grandparent": v.get("grandparent", "")}
                for k, v in exact_lookup.items()
            ]
            parents = list({v.get("parent", "") for v in exact_lookup.values() if v.get("parent")})
            grandparents = list({v.get("grandparent", "") for v in exact_lookup.values() if v.get("grandparent")})
            company_artifacts_loaded = True
    
    # 2) If company artifacts are incomplete or missing, try global artifacts
    if not company_artifacts_loaded:
        logger.info(f"Company artifacts not available, checking global artifacts in: {global_artifacts_dir}")
        exact_lookup = _load_exact_lookup_from_artifacts(global_artifacts_dir)
        if exact_lookup is not None:  # Only if all required files exist and loaded successfully
            logger.info(f"Loaded {len(exact_lookup)} entries from global artifacts")
            examples = [
                {"lineitem": k, "parent": v.get("parent", ""), "grandparent": v.get("grandparent", "")}
                for k, v in exact_lookup.items()
            ]
            parents = list({v.get("parent", "") for v in exact_lookup.values() if v.get("parent")})
            grandparents = list({v.get("grandparent", "") for v in exact_lookup.values() if v.get("grandparent")})
        else:
            logger.error("Global artifacts are also incomplete or missing")

    # 3) If no artifacts found, return empty results
    if not exact_lookup:
        logger.warning(f"No artifacts found in company or global directories")
        return {
            "company_code": company_code,
            "count": 0,
            "results": [],
            "message": "No artifacts found in company or global directories"
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
                _append_prediction_to_company_csv(csv_dir, code, line_item=line, parent=parent_val, grandparent=grand_val)
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
                _append_prediction_to_company_csv(csv_dir, code, line_item=line, parent=parent_val, grandparent=grand_val)
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


@app.post("/upload/extract_missing")
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
            raise HTTPException(status_code=400, detail=f"Failed to parse uploaded file: {e}")

    # drop rows/cols that are completely empty
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all").reset_index(drop=True)

    # must have rows
    if df.shape[0] == 0:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data after removing empty rows/columns.")

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
    parent_col = normalized_headers.get("parent")      # may be None
    grand_col = normalized_headers.get("grandparent") # may be None
    company_col = normalized_headers.get("companycode")# may be None

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
        raise HTTPException(status_code=400, detail="No non-empty values found in lineitem column.")

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

    parent_missing = df[parent_col].apply(is_missing_val) if parent_col else pd.Series([True] * len(df))
    grand_missing = df[grand_col].apply(is_missing_val) if grand_col else pd.Series([True] * len(df))

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

@app.post("/save")
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
                li = (r.get("line_item") or "").replace("\r", " ").replace("\n", " ").strip()
                p = (r.get("parent") or "").replace("\r", " ").replace("\n", " ").strip()
                g = (r.get("grandparent") or "").replace("\r", " ").replace("\n", " ").strip()
                
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
            headers={"csv_path": csv_path, "artifacts_dir": artifacts_dir}
        )

    return {
        "status": "ok",
        "csv_path": csv_path,
        "artifacts_dir": artifacts_dir,
        "rows_processed": len(req.rows),
        "total_rows": len(existing_lines)
    }