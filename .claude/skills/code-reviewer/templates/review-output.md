# Total Review Report: {FEATURE_NAME}

**Reviewer:** Total Review Engine (Dual-Pass)  
**Date:** {DATE}  
**Commits:** {BASE_SHA}..{HEAD_SHA}  
**Verdict:** {✅ Approved / ⚠️ Action Required / ❌ Blocked}

---

## 📋 Merged & Triaged Issues

### 🔴 Critical Consensus [both]
*(Выявлены обоими независимыми фокусами — наивысшая достоверность)*

1. **{Issue Title}**
   - **Location:** `{path/to/file.ts:line}`
   - **Problem:** {Description}
   - **Impact:** {Why this matters}
   - **Recommended Fix:** `{brief fix description or code}`

### 🟠 Specific Issues [logic] / [sec]
*(Выявлены профильным фокусом и прошли порог триажа)*

2. `[logic]` **{Issue Title}** (`{path/to/file.ts:line}`) — {Brief description + fix}
3. `[sec]` **{Issue Title}** (`{path/to/file.ts:line}`) — {Brief description + fix}

---

## 🧹 Triage Summary (Отсеянный оверсинкинг)

- **Отброшено замечаний:** {N} (субъективные вкусовые предпочтения, теоретические краевые случаи с P < 0.001%, микрооптимизации без профилирования).
- **Оставлено для утверждения:** {M} реальных дефектов.

---

## ✋ Approval Gate

```text
Перед применением изменений пользователь должен подтвердить список дефектов.
Автоматическое исправление вслепую ЗАПРЕЩЕНО.
```
