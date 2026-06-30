import os

def list_workspace_files() -> str:
    """
    List all non-ignored files and folders recursively in the project workspace.
    
    Returns:
        A string mapping out the project directory structure.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    try:
        lines = []
        for root, dirs, files in os.walk(project_root):
            # Prune directories starting with . or named .venv or __pycache__ in-place
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (".venv", "__pycache__")]
            
            # Filter files to ignore hidden files
            files = [f for f in files if not f.startswith(".")]
            
            rel_path = os.path.relpath(root, project_root)
            if rel_path == ".":
                display_name = "workspace"
                level = 0
            else:
                display_name = os.path.basename(root)
                level = rel_path.count(os.sep) + 1
                
            indent = '  ' * level
            lines.append(f"{indent}📁 {display_name}/")
            
            sub_indent = '  ' * (level + 1)
            for f in files:
                lines.append(f"{sub_indent}📄 {f}")
                
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing workspace files: {str(e)}"
