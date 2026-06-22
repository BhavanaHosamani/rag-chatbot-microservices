import os
from typing import List, Dict

# Safe base directory — all file ops confined here
BASE_DIR = "/tmp/mcp_files"


def _safe_path(path: str) -> str:
    """Ensure path stays within BASE_DIR to prevent directory traversal."""
    os.makedirs(BASE_DIR, exist_ok=True)
    # Strip leading slashes and resolve
    clean = path.lstrip("/").replace("..", "")
    full_path = os.path.join(BASE_DIR, clean)
    # Ensure it's inside BASE_DIR
    if not os.path.abspath(full_path).startswith(os.path.abspath(BASE_DIR)):
        raise ValueError("Access denied: path outside allowed directory.")
    return full_path


def read_file(path: str) -> str:
    """Read and return contents of a file."""
    try:
        full_path = _safe_path(path)
        if not os.path.exists(full_path):
            return f"Error: File '{path}' not found."
        if os.path.isdir(full_path):
            return f"Error: '{path}' is a directory, not a file."
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content if content else "(empty file)"
    except ValueError as e:
        return f"Error: {str(e)}"
    except UnicodeDecodeError:
        return f"Error: File '{path}' is not a text file."
    except Exception as e:
        return f"Error reading file: {str(e)}"


def write_file(path: str, content: str) -> str:
    """Write content to a file, creating directories as needed."""
    try:
        full_path = _safe_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File '{path}' written successfully ({len(content)} chars)."
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def list_files(path: str = "") -> List[Dict]:
    """List files and folders in a directory."""
    try:
        full_path = _safe_path(path) if path else BASE_DIR
        os.makedirs(full_path, exist_ok=True)

        if not os.path.isdir(full_path):
            return [{"error": f"'{path}' is not a directory."}]

        items = []
        for name in os.listdir(full_path):
            item_path = os.path.join(full_path, name)
            items.append({
                "name": name,
                "type": "directory" if os.path.isdir(item_path) else "file",
                "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None
            })

        return sorted(items, key=lambda x: (x["type"] == "file", x["name"]))

    except ValueError as e:
        return [{"error": str(e)}]
    except Exception as e:
        return [{"error": str(e)}]