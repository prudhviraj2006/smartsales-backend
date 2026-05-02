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
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV file: {str(e)}")

    if len(df) < 30:
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have at least 30 rows. Found: {len(df)}",
        )

    columns = df.columns.tolist()

    # Detect date column
    date_col = None
    for col in columns:
        try:
            pd.to_datetime(df[col], format="%Y-%m-%d", errors="raise")
            date_col = col
            break
        except (ValueError, TypeError):
            try:
                pd.to_datetime(df[col], errors="raise")
                date_col = col
                break
            except (ValueError, TypeError):
                continue

    if date_col is None:
        raise HTTPException(
            status_code=400,
            detail="No valid date column found. Ensure a column has YYYY-MM-DD format.",
        )

    # Detect numeric columns
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    
    # If no numeric columns found, try to detect "currency strings" that should be numeric
    if not numeric_cols:
        for col in columns:
            if col == date_col: continue
            # Check if column is mostly strings that look like numbers (with ₹, $, or ,)
            sample = df[col].dropna().head(10).astype(str)
            if sample.str.match(r'^[^\d]*[\d,\.]+[^\d]*$').all():
                numeric_cols.append(col)
                # Note: We don't modify the dataframe here, just identifying the column as numeric-capable

    if not numeric_cols:
        raise HTTPException(
            status_code=400,
            detail="No numeric columns found for Sales/Revenue data. Ensure your sales column contains numbers.",
        )

    return {
        "row_count": len(df),
        "columns": columns,
        "date_column": date_col,
        "numeric_columns": numeric_cols,
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
        "message": "Sample data uploaded successfully!",
    }
