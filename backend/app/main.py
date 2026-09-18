from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import auth, models
from app.routers import auth as auth_router
from app.routers import hardware as hardware_router
from app.routers import health
from app.routers import keyrate as keyrate_router
from app.routers import ml as ml_router
from app.routers import reports as reports_router
from app.routers import simulate as simulate_router


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
        "http://127.0.0.1:4173",  # vite preview on the loopback IP
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(auth_router.router, tags=["auth"])
# hardware BEFORE simulate: its static path /simulate/hardware must win over
# the dynamic /simulate/{protocol} route (registration order = match order).
app.include_router(hardware_router.router, tags=["hardware"])
app.include_router(simulate_router.router, tags=["simulate"])
app.include_router(ml_router.router, tags=["ml"])
app.include_router(keyrate_router.router, tags=["keyrate"])
app.include_router(reports_router.router, tags=["reports"])


@app.get("/")
def root() -> dict:
    return {"message": "Quantum Key Distribution API", "docs": "/docs"}
