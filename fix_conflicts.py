import os

def clean_conflict_markers(file_path):
    """
    Reads a file and removes git conflict markers, keeping the 'HEAD' (local) version
    and discarding the incoming version.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Skipping {file_path}: Unable to read ({e})")
        return False

    new_lines = []
    inside_conflict = False
    inside_ours = False
    found_conflict = False

    for line in lines:
        stripped = line.rstrip()
        
        # Start of a conflict block (Keep what follows)
        if stripped.startswith("<<<<<<<"):
            inside_conflict = True
            inside_ours = True
            found_conflict = True
            continue  # Skip the marker line itself

        # Middle of a conflict block (Switch to discarding what follows)
        if stripped.startswith("======="):
            if inside_conflict:
                inside_ours = False
                continue # Skip the marker line

        # End of a conflict block
        if stripped.startswith(">>>>>>>"):
            if inside_conflict:
                inside_conflict = False
                inside_ours = False # Reset
                continue # Skip the marker line

        # Decide whether to keep the line
        if inside_conflict:
            if inside_ours:
                new_lines.append(line)
            # else: we are in the 'theirs' section, so we drop the line
        else:
            new_lines.append(line)

    if found_conflict:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"FIXED: {file_path}")
            return True
        except Exception as e:
            print(f"ERROR writing {file_path}: {e}")
    
    return False

def main():
    # Get the current directory where this script is located
    root_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"Scanning for conflicts in: {root_dir}...\n")

    files_fixed = 0
    
    # Walk through all directories
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip .git and __pycache__ folders
        if '.git' in dirnames:
            dirnames.remove('.git')
        if '__pycache__' in dirnames:
            dirnames.remove('__pycache__')
            
        for filename in filenames:
            # Only check likely text/code files
            if filename.endswith(('.py', '.md', '.txt', '.json', '.html', '.css', '.js')):
                full_path = os.path.join(dirpath, filename)
                # Don't check this script itself
                if filename == "fix_conflicts.py":
                    continue
                
                if clean_conflict_markers(full_path):
                    files_fixed += 1

    print(f"\nScan complete. Fixed {files_fixed} files.")

if __name__ == "__main__":
    main()