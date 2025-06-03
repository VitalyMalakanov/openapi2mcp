import fastmcp as fmcp

print("--- dir(fmcp) ---")
print(dir(fmcp))
print("\n--- Accessing fmcp.Mcp ---")
try:
    McpClass = fmcp.Mcp
    print(f"Successfully accessed fmcp.Mcp: {McpClass}")
except AttributeError as e:
    print(f"AttributeError accessing fmcp.Mcp: {e}")

print("\n--- Accessing fmcp.server.Mcp (alternative) ---")
try:
    # If Mcp is in a submodule like 'server'
    from fastmcp.server import Mcp as ServerMcp
    print(f"Successfully accessed fmcp.server.Mcp: {ServerMcp}")
except ImportError:
    print("Could not import Mcp from fastmcp.server")
# except AttributeError as e: # AttributeError is already caught above generally
#     print(f"AttributeError accessing fmcp.server.Mcp: {e}")


# Check if 'mcp' (the dependency) is somehow shadowing things
print("\n--- Importing 'mcp' (the dependency) ---")
try:
    import mcp as mcp_dependency
    print(f"Imported mcp dependency: {mcp_dependency}")
    print(dir(mcp_dependency))
except ImportError:
    print("Could not import 'mcp' dependency directly.")
