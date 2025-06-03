from __future__ import annotations

import fastmcp as fmcp
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

from pydantic import BaseModel
from typing import List

class Employee(BaseModel):
    name: str | None = None
    id: int | None = None
    manages: List[Employee] | None = None
    reports_to: Employee | None = None
    department: Department | None = None

class Department(BaseModel):
    name: str | None = None
    id: int | None = None
    members: List[Employee] | None = None
    company: Company | None = None

class Company(BaseModel):
    name: str | None = None
    departments: List[Department] | None = None

app = fmcp.FastMCP(
    name="Cyclic Dependencies Test API",
    version="1.0.0",
    llm_tools=[]
)


# Register resources
# No resources to register

if __name__ == "__main__":
    app.run_stdio()
