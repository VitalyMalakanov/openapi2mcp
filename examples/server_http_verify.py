from __future__ import annotations

import sys
import fastmcp as fmcp
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class Pet(BaseModel):
    id: int
    name: str
    tag: str | None = None


# Resolve forward references
Pet.model_rebuild()

app = fmcp.FastMCP(
    name="Minimal Pet API Test",
    version="1.0.0",
    llm_tools=[]
)


@app.resource("pets/{petId}")
def show_pet_by_id(petId: str) -> Pet:
    """Info for a specific pet
    """
    pass # TODO: Implement actual logic

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print('Error: "uvicorn" is not installed. Please install it to use the http transport (e.g., pip install uvicorn)')
        sys.exit(1)
    uvicorn.run(app.http_app, host="0.0.0.0", port=8000)
