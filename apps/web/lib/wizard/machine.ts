import { setup, createMachine, assign } from "xstate";

/**
 * Машина состояний визарда запуска исследования (задача #7).
 *
 * 7 шагов: content → audience → survey → overlap_params → summary → launch → progress.
 * Переход вперёд запрещён, пока не заполнены обязательные поля шага.
 * Назад — свободно. Произвольный переход на будущий шаг запрещён.
 */

export interface WizardContext {
  mode: "short" | "long" | null;
  contentTitle: string;
  contentUrl: string;
  audienceSize: number;
  ageGroups: string[];
  geos: string[];
  /** Пол — обязательный критерий наравне с возрастом и гео (задача #9). */
  genders: string[];
  /** Незаземлённый критерий: поля education в корпусе нет. Не обязателен. */
  education: string[];
  /**
   * Выбранный существующий набор персон. Не null — генерации не будет,
   * и критерии на этом шаге не требуются (задача #9, второй пункт cdd).
   */
  personaSetId: string | null;
  surveyQuestions: unknown[];
  overlap: number;
  whisperModel: string;
  replicationCount: number;
  currentStep: number;
}

export type WizardEvent =
  | { type: "NEXT" }
  | { type: "BACK" }
  | { type: "GOTO"; step: number }
  | { type: "UPDATE"; data: Partial<WizardContext> };

const STEPS = [
  "content",
  "audience",
  "survey",
  "overlap_params",
  "summary",
  "launch",
  "progress",
] as const;

/** Обязательные поля для каждого шага. */
const REQUIRED: Record<string, (ctx: WizardContext) => boolean> = {
  content: (c) => !!c.contentTitle && !!c.contentUrl && !!c.mode,
  // Задача #9. Две ветки, а не одна с флагом:
  //
  // · выбран существующий набор — критерии не нужны, потому что генерации не
  //   будет. Требовать их значило бы заставлять заполнять то, что не будет
  //   использовано;
  //
  // · генерация — обязательны размер, возраст, гео И ПОЛ. Пол добавлен здесь:
  //   в корпусе он распределён 110/55 и участвует в калибровке, а в контексте
  //   машины его до этой задачи не было вовсе. Критерий, который есть в
  //   интерфейсе и ни на что не влияет, хуже отсутствующего.
  //
  // Образование не обязательно: оно незаземлено (поля нет в корпусе), и
  // блокировать им запуск было бы требованием заполнить то, что ни на что не
  // опирается.
  audience: (c) =>
    c.personaSetId !== null
      ? true
      : c.audienceSize > 0 &&
        c.ageGroups.length > 0 &&
        c.geos.length > 0 &&
        c.genders.length > 0,
  survey: (c) => true, // Опрос необязателен — можно пропустить
  overlap_params: (c) => c.overlap >= 0 && !!c.whisperModel && c.replicationCount > 0,
  summary: () => true,
  launch: () => true,
  progress: () => true,
};

function canProceed(ctx: WizardContext, step: number): boolean {
  if (step >= STEPS.length - 1) return false;
  const stepName = STEPS[step];
  const check = REQUIRED[stepName];
  return check ? check(ctx) : true;
}

export const wizardMachine = createMachine({
  id: "wizard",
  initial: "content",
  context: {
    mode: null,
    contentTitle: "",
    contentUrl: "",
    audienceSize: 20,
    ageGroups: [],
    geos: [],
    genders: [],
    education: [],
    personaSetId: null,
    surveyQuestions: [],
    overlap: 1,
    whisperModel: "large-v3",
    replicationCount: 1,
    currentStep: 0,
  } as WizardContext,
  states: {
    content: {
      on: {
        NEXT: { target: "audience", guard: ({ context }) => canProceed(context, 0) },
        BACK: undefined,
        UPDATE: { actions: assign(({ context, event }) => {
          if (event.type !== "UPDATE") return {};
          return { ...context, ...event.data };
        })},
      },
    },
    audience: {
      on: {
        NEXT: { target: "survey", guard: ({ context }) => canProceed(context, 1) },
        BACK: "content",
        UPDATE: { actions: assign(({ context, event }) => {
          if (event.type !== "UPDATE") return {};
          return { ...context, ...event.data };
        })},
      },
    },
    survey: {
      on: {
        NEXT: { target: "overlap_params", guard: ({ context }) => canProceed(context, 2) },
        BACK: "audience",
        UPDATE: { actions: assign(({ context, event }) => {
          if (event.type !== "UPDATE") return {};
          return { ...context, ...event.data };
        })},
      },
    },
    overlap_params: {
      on: {
        NEXT: { target: "summary", guard: ({ context }) => canProceed(context, 3) },
        BACK: "survey",
        UPDATE: { actions: assign(({ context, event }) => {
          if (event.type !== "UPDATE") return {};
          return { ...context, ...event.data };
        })},
      },
    },
    summary: {
      on: {
        NEXT: { target: "launch", guard: ({ context }) => canProceed(context, 4) },
        BACK: "overlap_params",
      },
    },
    launch: {
      on: {
        NEXT: { target: "progress", guard: ({ context }) => canProceed(context, 5) },
        BACK: "summary",
      },
    },
    progress: {
      on: {
        BACK: "launch",
      },
    },
  },
});

export { STEPS };