from fastmcp import FastMCP
mcp = FastMCP("Garmin Connect")
@mcp.tool
def connetion_test() -> str:
  """Check whether the Garmin MCP server is running."""
    return "Garmin MCP server is running successfully."
if __name__ == "__main__":
    mcp.run(
      transport="http",
      host="0.0.0.0",
      port=8000,
    )
