from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.simulation import router as simulation_router

app = FastAPI(title="Secure Model Platform API", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=False, allow_methods=["POST", "GET"], allow_headers=["Content-Type"])
app.include_router(simulation_router, prefix="/api")

@app.get("/api/health")
def health():
    return {"status": "ok"}
