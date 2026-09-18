from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health

app = FastAPI(
    title="Quantum Key Distribution API",
    version="0.1.0",
    description="QKD simulation backend: protocols, attacks, and ML models.",
)

# CORS for local dev (Vite default ports)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",  # vite preview
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])


@app.get("/")
def root() -> dict:
    return {"message": "Quantum Key Distribution API", "docs": "/docs"}
