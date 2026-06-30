import os

def read_local_file(filename: str) -> str:
    """
    Read the contents of a local text file within the project workspace.
    
    Args:
        filename: The relative path to the file from the workspace root (e.g., 'MILO_plan.md' or 'src/config.py').
        
    Returns:
        The content of the file, or an error message if access is denied or file not found.
    """
    # Safeguard against path traversal
    # Resolve the absolute path of the project root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    target_path = os.path.abspath(os.path.join(project_root, filename))
    
    # Check if target_path starts with project_root
    if not target_path.startswith(project_root):
        return "Error: Access denied. You cannot read files outside the project workspace."
        
    if not os.path.exists(target_path):
        return f"Error: File '{filename}' not found."
        
    if os.path.isdir(target_path):
        return f"Error: '{filename}' is a directory. Use list_dir_tool or specify a file."
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            # Limit read to first 10,000 characters to prevent overwhelming context
            content = f.read(10000)
            if len(content) == 10000:
                content += "\n... [Content Truncated to 10,000 chars]"
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}"
