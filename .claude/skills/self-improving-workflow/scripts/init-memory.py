#!/usr/bin/env python3
"""
Initialize .ai-memory/ structure for a project.

Usage:
    python3 init-memory.py [project-path]
    
Example:
    python3 init-memory.py .
    python3 init-memory.py /path/to/project
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_CONTEXT_TEMPLATE = '''# Project Context

**Project:** {project_name}
**Created:** {date}
**Last Updated:** {date}

---

## Overview

[Brief description of what this project does]

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | [e.g., TypeScript, Python] |
| Framework | [e.g., Next.js, FastAPI] |
| Database | [e.g., PostgreSQL, MongoDB] |
| Testing | [e.g., Jest, pytest] |
| Deployment | [e.g., Vercel, AWS] |

---

## Architecture

[High-level architecture description]

### Key Components

- **Component 1**: [description]
- **Component 2**: [description]
- **Component 3**: [description]

### Directory Structure

```
src/
├── ...
```

---

## Coding Conventions

### Naming
- Variables: [camelCase / snake_case]
- Functions: [camelCase / snake_case]
- Classes: [PascalCase]
- Files: [kebab-case / snake_case]

### Style
- Indentation: [2 spaces / 4 spaces / tabs]
- Line length: [80 / 100 / 120]
- Quotes: [single / double]

### Patterns
- Error handling: [describe approach]
- State management: [describe approach]
- API design: [describe approach]

---

## Common Tasks

### Task 1: [e.g., Adding a new feature]
[Brief steps or considerations]

### Task 2: [e.g., Running tests]
```bash
[command]
```

### Task 3: [e.g., Deployment]
[Brief steps]

---

## Gotchas & Known Issues

- [Known issue 1]
- [Known issue 2]

---

## External Dependencies

- [Dependency 1]: [purpose]
- [Dependency 2]: [purpose]

---

## Notes for AI Agent

### Do
- [Preferred approach 1]
- [Preferred approach 2]

### Don't
- [Anti-pattern 1]
- [Anti-pattern 2]

### Ask Before
- [Situations requiring confirmation]
'''

SCRATCHPAD_TEMPLATE = '''# Scratchpad

**Current Session:** {date}
**Task:** [current task]

---

## Current State

[What we're working on right now]

---

## Next Steps

- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

---

## Open Questions

- [question 1]

---

## Notes

[temporary notes, will be cleared next session]
'''

PATTERNS_TEMPLATE = '''# Accumulated Patterns

**Last Updated:** {date}

---

## Code Patterns

### Pattern 1: [name]
**When:** [trigger condition]
**Do:** [action]
```
[example code]
```

---

## Communication Patterns

### Pattern 1: [name]
**When user says:** [trigger]
**Agent should:** [response pattern]

---

## Anti-Patterns (Avoid)

### Anti-Pattern 1: [name]
**Problem:** [what goes wrong]
**Instead:** [correct approach]

---

## Project-Specific Learnings

- [learning 1]
- [learning 2]
'''

GITIGNORE_ENTRY = '''
# AI Memory (Self-Improving Workflow)
.ai-memory/
'''


def init_memory(project_path: str) -> None:
    """Initialize .ai-memory/ directory structure."""
    
    project_path = Path(project_path).resolve()
    
    if not project_path.is_dir():
        print(f"Error: Not a directory: {project_path}")
        sys.exit(1)
    
    memory_dir = project_path / ".ai-memory"
    project_name = project_path.name
    date = datetime.now().strftime("%Y-%m-%d")
    
    # Create directory
    memory_dir.mkdir(exist_ok=True)
    
    # Create files
    files = {
        "project-context.md": PROJECT_CONTEXT_TEMPLATE.format(
            project_name=project_name,
            date=date
        ),
        "scratchpad.md": SCRATCHPAD_TEMPLATE.format(date=date),
        "patterns.md": PATTERNS_TEMPLATE.format(date=date),
    }
    
    created = []
    skipped = []
    
    for filename, content in files.items():
        filepath = memory_dir / filename
        if filepath.exists():
            skipped.append(filename)
        else:
            filepath.write_text(content)
            created.append(filename)
    
    # Check/update .gitignore
    gitignore_path = project_path / ".gitignore"
    gitignore_updated = False
    
    if gitignore_path.exists():
        gitignore_content = gitignore_path.read_text()
        if ".ai-memory" not in gitignore_content:
            with open(gitignore_path, "a") as f:
                f.write(GITIGNORE_ENTRY)
            gitignore_updated = True
    else:
        gitignore_path.write_text(GITIGNORE_ENTRY.strip() + "\n")
        gitignore_updated = True
    
    # Report
    print(f"✅ AI Memory initialized: {memory_dir}")
    print()
    
    if created:
        print("Created:")
        for f in created:
            print(f"  ✓ {f}")
    
    if skipped:
        print("Skipped (already exist):")
        for f in skipped:
            print(f"  - {f}")
    
    if gitignore_updated:
        print()
        print("Updated .gitignore to exclude .ai-memory/")
    
    print()
    print("Next steps:")
    print("  1. Edit .ai-memory/project-context.md with your project details")
    print("  2. Start a session with: 'Read .ai-memory/ and apply learned patterns'")
    print("  3. End session with: 'Analyze session and save to .ai-memory/session-{date}.md'")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize .ai-memory/ structure for Self-Improving Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 init-memory.py .
  python3 init-memory.py /path/to/project
        """
    )
    parser.add_argument(
        "project_path", 
        nargs="?", 
        default=".",
        help="Path to project (default: current directory)"
    )
    
    args = parser.parse_args()
    init_memory(args.project_path)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
