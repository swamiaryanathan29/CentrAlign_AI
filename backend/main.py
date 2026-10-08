"""
Main FastAPI application — mounts both the agent API and ERP simulator.
"""
import os
import sys

# Make sure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from backend.routers.agent_router import router as agent_router
from backend.erp_sim.erp_app import erp_app

app = FastAPI(title="CentrAlign AI Worker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount agent API
app.include_router(agent_router)

# Mount ERP simulator under /erp (enables single-port deployment on Render/cloud)
app.mount("/erp", erp_app)

# Serve frontend — mount at root so relative asset URLs (style.css, app.js) resolve
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    # Serve index.html at root
    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    # Serve all other frontend assets (style.css, app.js, etc.) at their bare paths
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {"message": "CentrAlign AI Worker API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
