"""
Standalone ERP simulator runner.
Run: python -m backend.erp_sim.run_erp
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import uvicorn
from backend.erp_sim.erp_app import erp_app

if __name__ == "__main__":
    uvicorn.run(erp_app, host="0.0.0.0", port=8001)
