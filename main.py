"""
SmartSales AI – FastAPI Backend Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api import auth, upload, forecast, insights, chat

app = FastAPI(
    title="SmartSales AI API",
    description="AI Sales Forecaster & Business Insight Generator",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(forecast.router)
app.include_router(insights.router)
app.include_router(chat.router)


@app.on_event("startup")
async def startup():
    init_db()
    from app.core.database import SessionLocal
    from app.models.schemas import User
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == 1).first()
        if not user:
            mock_user = User(
                id=1,
                email="test@example.com",
                password_hash="fakehash",
                full_name="Bypass User"
            )
            db.add(mock_user)
            db.commit()
    finally:
        db.close()


@app.get("/")
def root():
    return {
        "app": "SmartSales AI",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
