# packages/shared — общий контракт TS ↔ Python

Decision Log #4: единственный источник истины для типов, которые пересекают границу
между `apps/web` (TypeScript) и `services/agent-core` (Python), — **canonical JSON Schema**
в `schemas/`. Из неё генерируются TS-типы и Pydantic-модели; руками ни те, ни другие
не правятся.

```
schemas/            canonical JSON Schema — источник истины
  persona-dna.schema.json      8 категорий Persona DNA (задача #4)
  survey.schema.json           анкета и типы вопросов (#10)
  pipeline-state.schema.json   состояние LangGraph (#13)
  report.schema.json           отчёт: агрегат + per_persona (#20, #21)
generated/
  ts/                генерируется в apps/web
  python/            генерируется в services/agent-core
```

На задаче #1 здесь только каркас и это правило. Наполнение схем — задачи #4, #10, #13, #20.

## Почему схема, а не два независимых определения
Персона проходит путь: сгенерирована в Python → сохранена в Postgres → отрендерена
карточкой в TS → снова прочитана Python'ом при допросе персоны в чате (#28). Любое
расхождение типов на этом пути даёт молчаливую потерю полей — ровно то, что CDD-тест
задачи #6 обязан ловить сверкой отрендеренных полей со схемой.
