import os
import sys

def fix_future_imports(directories):
    for directory in directories:
        for root, dirs, files in os.walk(directory):
            # Skip virtual environments and git
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'venv', 'env')]
            
            for file in files:
                if not file.endswith('.py'):
                    continue
                    
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception:
                    continue
                    
                if 'from __future__ import annotations' not in content:
                    continue
                    
                lines = content.split('\n')
                
                # Check if it's already line 1 (index 0) and there's no docstring above it
                if len(lines) > 0 and lines[0] == 'from __future__ import annotations':
                    continue
                    
                # Remove all existing future annotations imports
                new_lines = [line for line in lines if line.strip() != 'from __future__ import annotations']
                
                # Find insertion point
                insert_idx = 0
                if new_lines and new_lines[0].startswith('#!'):
                    insert_idx = 1
                
                # Insert the import at the very top (or after shebang)
                new_lines.insert(insert_idx, 'from __future__ import annotations')
                
                # Write back
                new_content = '\n'.join(new_lines)
                if new_content != content:
                    print(f"Fixed {file_path}")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)

if __name__ == '__main__':
    fix_future_imports(['d:/python/nanobot/nanobot', 'd:/python/nanobot/bff'])
