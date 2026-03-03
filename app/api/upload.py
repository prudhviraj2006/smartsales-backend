"""
Upload API Router – CSV file upload and validation.
"""
import os
import uuid
import pandas as pd
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
    if not numeric_cols:
        raise HTTPException(
            status_code=400,
            detail="No numeric columns found for Sales/Revenue data.",
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
    # Validate file type
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    # Read content
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit.")

    # Save file
    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
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
