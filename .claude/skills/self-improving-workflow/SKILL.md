---
name: Self-Improving Workflow
description: Continuous learning system that creates feedback loops across AI sessions. Use at the START of any session to load accumulated context, and at the END to capture learnings. After 3-5 iterations, the agent stabilizes approach to your codebase and working style. Creates .ai-memory/ directory with session artifacts, patterns, and improvements.
created: 2026-02-08
last_updated: 2026-02-18
---

# Self-Improving Workflow

Create a feedback loop where each AI session generates artifacts (context, patterns, edge cases) that automatically load into the next session.

**Goal:** After 3-5 iterations → agent stabilizes approach to YOUR codebase and style.

---

## Quick Start

### Initialize (once per project)

```bash
# Run init script
python3 scripts/init-memory.py [project-path]

# Or manually
mkdir -p .ai-memory
echo "*.ai-memory" >> .gitignore  # or commit to personal/ branch
```

### Start Session

**Prompt:**
> Прочитай все файлы в `.ai-memory/` для этого проекта. Примени выявленные паттерны и избегай описанных ошибок. Если видишь противоречия между разными сессиями — уточни, какой подход предпочтительнее.

### End Session

**Prompt:**
> Проанализируй нашу текущую сессию. Выдели:
> 1. Ключевые решения и их обоснование
> 2. Edge cases и gotchas, с которыми мы столкнулись
> 3. Повторяющиеся паттерны запросов
> 4. Конкретные улучшения для твоего подхода к этой кодовой базе
>
> Запиши это в `.ai-memory/session-{YYYY-MM-DD-HH-MM}.md`

---

## Infrastructure Setup

### Worktree Isolation

```bash
# One VSCode instance per worktree
# Each task = separate worktree with clean commit history

# Shell alias for quick setup
alias ai-task='f() { 
  git worktree add ../task-$1 && 
  cd ../task-$1 && 
  mkdir -p .ai-memory && 
  cp ../.ai-memory/project-context.md .ai-memory/ 2>/dev/null
  echo "✅ Ready for AI session: task-$1"
}; f'

# Usage: ai-task auth-feature
```

### Git Strategy Options

| Option | When to Use |
|--------|------------|
| `.gitignore` | Personal notes, not shared |
| `personal/` branch | Shared across your devices |
| Orphan branch `ai-context` | Separate history |
| Monorepo `personal/` folder | Team-visible but personal |

---

## Directory Structure

```
.ai-memory/
├── project-context.md      # Архитектура, conventions, tech stack
├── scratchpad.md           # Текущий рабочий контекст (перезаписывается)
├── session-2026-02-08.md   # Конкретные решения, gotchas
├── session-2026-02-09.md
├── helpers-frontend.md     # Стабилизированные сниппеты (после 3+ сессий)
├── helpers-api.md
└── patterns.md             # Накопленные паттерны (создаётся автоматически)
```

---

## File Purposes

| Файл | Назначение | Обновление |
|------|------------|------------|
| `project-context.md` | Общая архитектура, conventions, tech stack | Ручное, при старте |
| `session-{date}.md` | Решения, gotchas, hyperparameters | Auto, end of session |
| `helpers-{domain}.md` | Стабилизированные сниппеты, templates | После 3+ схожих сессий |
| `scratchpad.md` | Временные заметки | Перезаписывается |
| `patterns.md` | Накопленные паттерны | Agent updates |

---

## Session File Structure

```markdown
# Session {YYYY-MM-DD}

**Task:** [brief description]
**Duration:** [approximate]
**Worktree:** [if applicable]

## Context
[What was the starting point, what were we trying to achieve]

## Decisions
- **Decision 1**: [what] — [why]
- **Decision 2**: [what] — [why]

## Edge Cases & Gotchas
- [gotcha 1]
- [gotcha 2]

## Patterns
- [recurring pattern observed]

## Improvements for Next Time
- [specific improvement for agent's approach]
- [what to do differently]

## Code Snippets Worth Remembering
```{language}
[useful code that might be reused]
```
```

---

## Adoption Phases

### Phase 1: Start (Sessions 1-3)
- Create `.ai-memory/` with `project-context.md`
- **Критично:** В конце КАЖДОЙ сессии явно документировать learnings
- Без этого — бесполезный noise вместо паттернов

### Phase 2: Stabilization (Sessions 4-10)
- Agent начнёт говорить "Based on previous sessions, I suggest..."
- Создать `helpers-{domain}.md` для reusable components
- Agent сам предложит категоризацию

### Phase 3: Routine (10+ Sessions)
- Новый worktree с одной командой
- Agent автоматически применяет ваш стиль
- Минимум уточняющих вопросов

---

## Success Metrics

| Метрика | Начало | После 10 сессий |
|---------|--------|-----------------|
| Time-to-first-commit | 30 min | 5 min |
| Уточняющих вопросов | Много | Минимум |
| Agent предлагает правильное решение до вашего запроса | Редко | Часто |

---

## Anti-Patterns (ИЗБЕГАТЬ)

| ❌ Не делать | ✅ Делать вместо |
|-------------|------------------|
| Читать/редактировать заметки вручную | Позволить агенту читать их |
| Создавать сложную структуру заранее | Начать с flat list, агент предложит категоризацию |
| Коммитить в main branch | Orphan branch `ai-context` или personal fork |
| Пропускать end-of-session документацию | Всегда документировать (критический mass) |

---

## Integration with Worktrees

```bash
# Shell alias для быстрого старта
alias ai-worktree='f() { 
  git worktree add ../$1 && 
  cd ../$1 && 
  mkdir -p .ai-memory && 
  cp ../.ai-memory/project-context.md .ai-memory/ 2>/dev/null
  echo "Ready for AI session in $1"
}; f'

# Usage
ai-worktree feature-auth
```

---

## Scripts

- `scripts/init-memory.py` — Initialize .ai-memory/ structure
- `scripts/save-session.py` — Save session artifacts with timestamp
- `scripts/start-session.py` — Generate context summary for new session

See individual script files for usage.

---

## Git Hooks (Optional)

Auto-commit `.ai-memory/` changes:

```bash
# .git/hooks/post-commit
#!/bin/bash
if git diff --cached --name-only | grep -q "^\.ai-memory/"; then
  git add .ai-memory/
  git commit --amend --no-edit
fi
```

---

## Prompt Templates

### Start Session (Full)
```
Прочитай все файлы в .ai-memory/:
1. project-context.md — общая архитектура
2. Последние 3 session-*.md — недавние решения
3. helpers-*.md — стабилизированные паттерны
4. patterns.md — накопленные инсайты

Примени выявленные паттерны. Избегай описанных gotchas.
При противоречиях — уточни предпочтительный подход.

Готов к работе? Опиши что ты узнал из контекста.
```

### End Session (Full)
```
Проанализируй нашу сессию и создай session-{timestamp}.md:

## Context
[starting point, goal]

## Decisions
- Decision: [что] — [почему]

## Edge Cases & Gotchas  
- [что не сработало и почему]

## Patterns
- [повторяющиеся паттерны]

## Improvements for Next Time
- [конкретные улучшения для подхода]

## Snippets
[полезный код для переиспользования]

Также обнови patterns.md если есть новые устойчивые паттерны.
```

### Mid-Session Checkpoint
```
Запиши текущее состояние в scratchpad.md:
- Что делаем
- Где остановились  
- Следующие шаги
- Открытые вопросы
```
