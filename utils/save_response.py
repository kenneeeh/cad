import os
from pathlib import Path
from google.genai import types

def writeMd(response: types.GenerateContentResponse, filename: str = "output.md"):
    """
    Writes the given markdown string to 'output.md' in the current directory
    and prints a clickable file URI link to open it in VS Code.

    Args:
        my_markdown (str): The markdown content to write to the file.
    """

    # default path
    project_dir = Path(__file__).parent.parent
    path = os.path.join(project_dir, "no_backup", "markdown_files")

    md_string = ""
    # monitoring the thinking summary and the final answer
    for part in response.candidates[0].content.parts:
        if not part.text:
            continue
        if part.thought:
            md_string += f"# Thought Summary\n{part.text}\n"
        else:
            md_string += f"# Answer Text\n{part.text}\n"

    # 2. Get the full, absolute path
    #    Path.resolve() makes it a full path like /home/user/project/output.md
    filepath = Path(path, filename).resolve()

    # 3. Write the markdown to the file
    filepath.write_text(md_string)

    # 4. Convert the path to a clickable file URI
    #    This turns it into file:///home/user/project/output.md
    file_uri = filepath.as_uri()

    # 5. Print the link for the user
    print("\n" + "="*30)
    print(f"\n{file_uri}\n")
    print("="*30 + "\n")