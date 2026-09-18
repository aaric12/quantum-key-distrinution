from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import auth, models
from app.routers import auth as auth_router
from app.routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.create_all()
    yield


app = FastAPI(
    title="Quantum Key Distribution API",
    version="0.1.0",
    description="QKD simulation backend: protocols, attacks, and ML models.",
    lifespan=lifespan,
)

# Rate limiting (slowapi): register the shared limiter and its 429 handler.
app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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
app.include_router(auth_router.router, tags=["auth"])


@app.get("/")
def root() -> dict:
    return {"message": "Quantum Key Distribution API", "docs": "/docs"}
