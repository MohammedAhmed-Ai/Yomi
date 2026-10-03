from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from app.db import engine, Base
from app.routers import carry_over, days, tasks, tags, stats

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Yomi API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/api/health", tags=["system"])
async def health_check():
    return {"status": "ok"}

# Register routers under /api
app.include_router(carry_over.router, prefix="/api")
app.include_router(days.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(tags.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
