#!/usr/bin/env python3
"""
Save current session artifacts to .ai-memory/

Usage:
    python3 save-session.py [project-path] [--task "task description"]
    
Example:
    python3 save-session.py . --task "Implemented user auth"
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


SESSION_TEMPLATE = '''# Session {timestamp}

**Task:** {task}
**Date:** {date}
**Time:** {time}

---

## Context

[What was the starting point, what were we trying to achieve]

---

## Decisions

- **Decision 1**: [what] — [why]
- **Decision 2**: [what] — [why]

---

## Edge Cases & Gotchas

- [gotcha 1 encountered during this session]
- [gotcha 2]

---

## Patterns

- [recurring pattern observed]

---

## Improvements for Next Time

- [specific improvement for agent's approach]
- [what to do differently]

---

## Code Snippets Worth Remembering

```
[useful code that might be reused]
```

---

## Files Changed

[list of files modified during this session]

---

## Open Questions

- [any unresolved questions for next session]
'''


def save_session(project_path: str, task: str = "Untitled Session") -> None:
    """Save session artifacts."""
    
    project_path = Path(project_path).resolve()
    memory_dir = project_path / ".ai-memory"
    
    if not memory_dir.is_dir():
        print(f"Error: .ai-memory/ not found in {project_path}")
        print("Run init-memory.py first")
        sys.exit(1)
    
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d-%H-%M")
    date = now.strftime("%Y-%m-%d")
    time = now.strftime("%H:%M")
    
    filename = f"session-{timestamp}.md"
    filepath = memory_dir / filename
    
    content = SESSION_TEMPLATE.format(
        timestamp=timestamp,
        task=task,
        date=date,
        time=time
    )
    
    filepath.write_text(content)
    
    print(f"✅ Session saved: {filepath}")
    print()
    print("Next steps:")
    print(f"  1. Fill in the session details in {filename}")
    print("  2. Or ask AI: 'Analyze our session and fill in session-{}.md'".format(timestamp))
    print()
    print("Prompt for AI to fill:")
    print("-" * 40)
    print(f"Analyze our current session. Fill in .ai-memory/{filename} with:")
    print("- Context: what we started with")
    print("- Decisions: key choices and reasoning")
    print("- Edge Cases: gotchas encountered")
    print("- Patterns: recurring patterns observed")
    print("- Improvements: what to do better next time")
    print("- Snippets: useful code to remember")


def main():
    parser = argparse.ArgumentParser(
        description="Save session artifacts to .ai-memory/",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "project_path", 
        nargs="?", 
        default=".",
        help="Path to project (default: current directory)"
    )
    parser.add_argument(
        "--task", "-t",
        default="Untitled Session",
        help="Brief description of the task"
    )
    
    args = parser.parse_args()
    save_session(args.project_path, args.task)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
