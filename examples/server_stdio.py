from __future__ import annotations

import fastmcp as mcp
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

from pydantic import BaseModel

class Pet(BaseModel):
    id: int
    name: str
    tag: str | None = None

class Error(BaseModel):
    code: int
    message: str

app = mcp.Mcp(
    name="Example Pet Store API",
    version="1.0.1",
    llm_tools=[create_pet, update_pet, delete_pet]
)


@app.resource
def list_pets(limit: int | None = None) -> List[Pet]:
    """List all pets

        Returns a list of all pets in the store. Supports pagination using the 'limit' parameter.
    """
    pass  # TODO: Implement actual logic


@app.resource
def show_pet_by_id(pet_id: str, version: str | None = None) -> Pet:
    """Info for a specific pet

        Retrieves the details of a specific pet by its ID.
    """
    pass  # TODO: Implement actual logic


@app.tool
def create_pet(ctx: mcp.Context, pet: Pet) -> Pet:
    """Create a pet

        Creates a new pet in the store.
    """
    pass  # TODO: Implement actual logic. Consider using ctx.sample() for LLM interaction.


@app.tool
def update_pet(ctx: mcp.Context, pet_id: str, pet: Pet) -> Pet:
    """Update an existing pet

        Updates an existing pet by ID.
    """
    pass  # TODO: Implement actual logic. Consider using ctx.sample() for LLM interaction.


@app.tool
def delete_pet(ctx: mcp.Context, pet_id: str) -> None:
    """Deletes a pet

        Deletes a specific pet by its ID.
    """
    pass  # TODO: Implement actual logic. Consider using ctx.sample() for LLM interaction.


# Register resources
if 'list_pets' in locals():
    app.add_resource(list_pets)
if 'show_pet_by_id' in locals():
    app.add_resource(show_pet_by_id)

if __name__ == "__main__":
    app.run_stdio()
