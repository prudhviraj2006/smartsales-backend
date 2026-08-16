"""
Upload API Router – CSV file upload and validation.
"""
import os
import uuid
import pandas as pd
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models.schemas import UploadedFile

router = APIRouter(prefix="/api", tags=["Upload"])


def validate_csv(file_path: str) -> dict:
    """Validate CSV file structure and content."""
    try:
        df = pd.read_csv(file_path)
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(file_path, encoding='ISO-8859-1')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV encoding: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV file: {str(e)}")

    if len(df) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have at least 5 rows. Found: {len(df)}",
        )

    columns = df.columns.tolist()

    # Detect date column (sample first 100 rows to prevent hanging)
    date_col = None
    for col in columns:
        col_lower = str(col).strip().lower()
        # Skip purely numeric columns from date parsing unless column name explicitly contains date keywords
        if pd.api.types.is_numeric_dtype(df[col]) and not ('date' in col_lower or 'time' in col_lower or col_lower == 'year' or col_lower == 'ds'):
            continue

        sample = df[col].dropna().head(100)
        if sample.empty:
            continue
        
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_col = col
            break

        try:
            pd.to_datetime(sample, format="%Y-%m-%d", errors="raise")
            date_col = col
            break
        except (ValueError, TypeError):
            try:
                pd.to_datetime(sample, errors="raise")
                date_col = col
                break
            except (ValueError, TypeError):
                continue

    # Classify each column into: "id", "date", "numeric", "text"
    columns_with_types = []
    numeric_value_cols = []

    for col in columns:
        col_lower = str(col).strip().lower()

        # Check if ID column (Row ID, Customer ID, Postal Code, Order ID, etc.)
        is_id = (
            'id' in col_lower or
            'postal' in col_lower or
            'zip' in col_lower or
            'code' in col_lower or
            col_lower == 'row' or
            col_lower == '#' or
            col_lower.endswith('_id')
        )

        # Check if date column
        is_date = (
            col == date_col or
            'date' in col_lower or
            'time' in col_lower or
            col_lower == 'ds' or
            col_lower == 'year' or
            col_lower == 'month' or
            col_lower == 'day'
        )

        if is_id:
            columns_with_types.append({"name": col, "type": "id"})
        elif is_date:
            columns_with_types.append({"name": col, "type": "date"})
        else:
            # Check numeric value type
            is_num = False
            if pd.api.types.is_numeric_dtype(df[col]):
                is_num = True
            else:
                # Check if currency string or numeric text ($1,234.50)
                sample = df[col].dropna().head(20).astype(str)
                if not sample.empty:
                    cleaned = sample.str.replace(r'[\$,₹%,\s]', '', regex=True)
                    if cleaned.str.replace('.', '', regex=False).str.isnumeric().all():
                        is_num = True

            if is_num:
                columns_with_types.append({"name": col, "type": "numeric"})
                numeric_value_cols.append(col)
            else:
                columns_with_types.append({"name": col, "type": "text"})

    return {
        "row_count": len(df),
        "columns": columns,
        "date_column": date_col,
        "numeric_columns": numeric_value_cols,
        "columns_with_types": columns_with_types,
    }


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Read content
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File size exceeds {settings.MAX_FILE_SIZE // (1024*1024)}MB limit.")

    # Validate file type (be lenient but check if it's likely text/csv)
    content_type = file.content_type or ""
    if not (file.filename.lower().endswith(".csv") or file.filename.lower().endswith(".txt") or "csv" in content_type.lower()):
        # Try to read first few bytes to see if it's text
        try:
            content.decode('utf-8')[:100]
        except Exception:
             raise HTTPException(status_code=400, detail="Uploaded file is not a valid text-based CSV.")

    # Save file
    # Sanitize filename (more lenient)
    import re
    safe_filename = re.sub(r'[^\w\s\.-]', '', file.filename).strip()
    if not safe_filename:
        safe_filename = "data.csv"
    
    unique_name = f"{uuid.uuid4().hex}_{safe_filename.replace(' ', '_')}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_name)
    
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(content)

    # Validate CSV
    try:
        validation = validate_csv(file_path)
    except HTTPException:
        os.remove(file_path)
        raise

    # Save record
    uploaded = UploadedFile(
        user_id=current_user["user_id"],
        filename=unique_name,
        original_filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        row_count=validation["row_count"],
        column_names=validation["columns"],
        date_column=validation["date_column"],
        target_column=None,
    )
    db.add(uploaded)
    db.commit()
    db.refresh(uploaded)

    return {
        "id": uploaded.id,
        "filename": file.filename,
        "row_count": validation["row_count"],
        "columns": validation["columns"],
        "date_column": validation["date_column"],
        "numeric_columns": validation["numeric_columns"],
        "columns_with_types": validation["columns_with_types"],
        "message": "File uploaded successfully!",
    }


@router.get("/files")
def list_files(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    files = (
        db.query(UploadedFile)
        .filter(UploadedFile.user_id == current_user["user_id"])
        .order_by(UploadedFile.uploaded_at.desc())
        .all()
    )
    return [
        {
            "id": f.id,
            "filename": f.original_filename,
            "row_count": f.row_count,
            "columns": f.column_names,
            "date_column": f.date_column,
            "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
        }
        for f in files
    ]

class TextUploadRequest(BaseModel):
    csv_text: str
    filename: Optional[str] = "manual_upload.csv"

class Base64UploadRequest(BaseModel):
    base64_data: str
    filename: Optional[str] = "uploaded_data.csv"

@router.post("/upload/base64")
def upload_csv_base64(
    req: Base64UploadRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import base64, re
    if not req.base64_data or len(req.base64_data.strip()) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file data cannot be empty.")

    raw_b64 = req.base64_data
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        file_bytes = base64.b64decode(raw_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 encoding: {str(e)}")

    safe_filename = re.sub(r'[^\w\s\.-]', '', req.filename or "uploaded_data.csv").strip()
    if not safe_filename:
        safe_filename = "uploaded_data.csv"

    unique_name = f"{uuid.uuid4().hex}_{safe_filename.replace(' ', '_')}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_name)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    try:
        validation = validate_csv(file_path)
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    uploaded = UploadedFile(
        user_id=current_user["user_id"],
        filename=unique_name,
        original_filename=req.filename,
        file_path=file_path,
        file_size=len(file_bytes),
        row_count=validation["row_count"],
        column_names=validation["columns"],
        date_column=validation["date_column"],
        target_column=None,
    )
    db.add(uploaded)
    db.commit()
    db.refresh(uploaded)

    return {
        "id": uploaded.id,
        "filename": req.filename,
        "row_count": validation["row_count"],
        "columns": validation["columns"],
        "date_column": validation["date_column"],
        "numeric_columns": validation["numeric_columns"],
        "columns_with_types": validation["columns_with_types"],
        "message": "Data uploaded successfully!",
    }

@router.post("/upload/text")
def upload_csv_text(
    req: TextUploadRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not req.csv_text or len(req.csv_text.strip()) == 0:
        raise HTTPException(status_code=400, detail="CSV text cannot be empty.")

    unique_name = f"{uuid.uuid4().hex}_{req.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_name)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(req.csv_text)

    try:
        validation = validate_csv(file_path)
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    uploaded = UploadedFile(
        user_id=current_user["user_id"],
        filename=unique_name,
        original_filename=req.filename,
        file_path=file_path,
        file_size=len(req.csv_text),
        row_count=validation["row_count"],
        column_names=validation["columns"],
        date_column=validation["date_column"],
        target_column=None,
    )
    db.add(uploaded)
    db.commit()
    db.refresh(uploaded)

    return {
        "id": uploaded.id,
        "filename": req.filename,
        "row_count": validation["row_count"],
        "columns": validation["columns"],
        "date_column": validation["date_column"],
        "numeric_columns": validation["numeric_columns"],
        "columns_with_types": validation["columns_with_types"],
        "message": "Manual data uploaded successfully!",
    }

@router.post("/upload/sample")
def upload_sample_data(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import datetime, math, random

    csv_data = "date,sales,category,region\n"
    categories = ["Electronics", "Clothing", "Food", "Home"]
    regions = ["North", "South", "East", "West"]
    start_date = datetime.date(2024, 1, 1)

    for i in range(365):
        d = start_date + datetime.timedelta(days=i)
        base_sales = 1000 + math.sin(i * 0.017) * 300
        sales = round(base_sales + random.uniform(0, 200))
        cat = categories[i % len(categories)]
        region = random.choice(regions)
        csv_data += f"{d.isoformat()},{sales},{cat},{region}\n"

    unique_name = f"{uuid.uuid4().hex}_sample_sales_data.csv"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_name)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(csv_data)

    validation = validate_csv(file_path)

    uploaded = UploadedFile(
        user_id=current_user["user_id"],
        filename=unique_name,
        original_filename="sample_sales_data.csv",
        file_path=file_path,
        file_size=len(csv_data),
        row_count=validation["row_count"],
        column_names=validation["columns"],
        date_column=validation["date_column"],
        target_column=None,
    )
    db.add(uploaded)
    db.commit()
    db.refresh(uploaded)

    return {
        "id": uploaded.id,
        "filename": "sample_sales_data.csv",
        "row_count": validation["row_count"],
        "columns": validation["columns"],
        "date_column": validation["date_column"],
        "numeric_columns": validation["numeric_columns"],
        "columns_with_types": validation["columns_with_types"],
        "message": "Sample data uploaded successfully!",
    }
