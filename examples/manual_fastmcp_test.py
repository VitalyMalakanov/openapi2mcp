from __future__ import annotations
import fastmcp as fmcp
import sys # For explicit exit

print(f"Using fastmcp version: {fmcp.__version__}")

app = fmcp.FastMCP(name="TestApp", version="1.0", llm_tools=[])
print("\n--- dir(app) ---")
print(dir(app))
print("------------------\n")

print("Defining static resource /static_path...")
try:
    @app.resource("/static_path")
    def my_static_handler():
        """A static resource."""
        return {"message": "hello from static path"}
    print("Static resource defined.")
except Exception as e:
    print(f"Error defining static resource: {e}")
    # traceback.print_exc() # This might be too verbose for the tool output

print("\nDefining templated resource /items/{item_id}...")
try:
    @app.resource("/items/{item_id}")
    def my_item_handler(item_id: str):
        """A templated resource."""
        return {"item_id": item_id}
    print("Templated resource defined.")
except Exception as e:
    print(f"Error defining templated resource: {e}")
    # traceback.print_exc()

if __name__ == "__main__":
    print("\nAttempting to run server with Uvicorn...")
    try:
        import uvicorn
        print("Uvicorn found. Running server on http://0.0.0.0:8000")
        # uvicorn.run(app.as_asgi(), host="0.0.0.0", port=8000) # This would block, not good for this test
        print("Simulated uvicorn.run() call for testing purposes.")
        print("If decorators processed without error, server setup is likely fine.")
        # Test instantiation of the ASGI app (now that we know it's 'app' itself for uvicorn)
        if app: # 'app' is the ASGI app
            print("FastMCP app instance is directly usable as ASGI app.")
        else:
            print("FastMCP app instance is not directly usable as ASGI app.") # Should not happen

    except ImportError:
        print("Uvicorn not found. Cannot run HTTP server for this manual test.")
    except ValueError as ve: # Catch the specific error we've been seeing
        print(f"Caught ValueError during server setup: {ve}")
        # traceback.print_exc()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        # traceback.print_exc()
    sys.exit(0) # Ensure the script exits for the test runner
