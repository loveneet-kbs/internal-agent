"""Dev entrypoint:  python run.py

Production:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=settings.port,
        reload=True,
        reload_dirs=["app"],
    )
