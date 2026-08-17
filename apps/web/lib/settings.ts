/**
 * Настройки арендатора (задача #27, PRD §12).
 *
 * Этот модуль — контракт между интерфейсом, API-роутом и воркером. Он специально
 * вынесен из компонента: воркер обязан читать ровно те же имена полей и ровно тот
 * же список допустимых значений, иначе выбор в интерфейсе разойдётся с тем, что
 * реально исполняется. Валидация здесь, а не в компоненте, по той же причине —
 * запись в БД должна отвергать мусор независимо от того, кто её прислал.
 *
 * Хранение: таблица settings в Postgres, scoped по tenant_id через RLS
 * (задача #2 + #3). До появления auth роут работает с одним арендатором.
 */

/** Модели транскрипции. Список закрыт: воркер грузит веса по этому идентификатору. */
export const WHISPER_MODELS = ["large-v3", "large-v3-turbo"] as const;
export type WhisperModel = (typeof WHISPER_MODELS)[number];

export const COST_CAP_MODES = ["auto", "hard"] as const;
export type CostCapMode = (typeof COST_CAP_MODES)[number];

export const REPLICATION_VALUES = [1, 3, 5] as const;
export type ReplicationCount = (typeof REPLICATION_VALUES)[number];

/**
 * ─── Температура по стадиям ────────────────────────────────────────────────
 *
 * Одного значения на весь конвейер быть не может: стадии требуют
 * противоположного. Персона обязана получиться непохожей на соседнюю — это
 * условие метрики `response_diversity`, и низкая температура здесь даёт mode
 * collapse, то есть двадцать почти совпадающих портретов. Проверяющий же и
 * аналитик обязаны быть повторяемыми: вердикт, который меняется от прогона к
 * прогону, перестаёт быть свойством проверяемого.
 *
 * Ключи совпадают с полями `TemperatureConfig` воркера
 * (services/agent-core/agent_core/config.py). Разойдясь, они дали бы настройку,
 * которая выставляется и не применяется, — а увидеть это можно было бы только
 * по счёту от провайдера и по доле отбраковок.
 */
export const TEMPERATURE_STAGES = [
  {
    key: "personaCreation",
    label: "Создание персоны из датасета",
    default: 0.9,
    recommended: "0.7–1.0",
    hint:
      "Нужна вариативность формулировок и нюансов, чтобы персона не была " +
      "«шаблонной» копией среднего пользователя.",
  },
  {
    key: "personaValidation",
    label: "Валидация персоны QA-агентом",
    default: 0.1,
    recommended: "0–0.3",
    hint:
      "Здесь важна повторяемость: одна и та же персона не должна «плыть» " +
      "между прогонами.",
  },
  {
    key: "responseSimulation",
    label: "Симуляция ответов персоной",
    default: 0.3,
    recommended: "0.3–0.6",
    hint:
      "Баланс: достаточно живости в ответах, но без потери связности и логики " +
      "персонажа; слишком высокая температура даёт шум и потерю индивидуального голоса.",
  },
  {
    key: "aggregation",
    label: "Агрегация и анализ результатов",
    default: 0.1,
    recommended: "0–0.2",
    hint:
      "Нужна максимальная детерминированность и точность выводов, без " +
      "творческих искажений.",
  },
  {
    key: "answerJudge",
    label: "Проверка ответов QA-судьёй",
    default: 0,
    recommended: "0–0.2",
    hint:
      "Два прогона QA по одному ответу обязаны давать один вердикт, иначе " +
      "«ответ забракован» перестаёт быть свойством ответа.",
  },
  {
    key: "segmentPortraits",
    label: "Портреты сегментов",
    default: 0.3,
    recommended: "0.2–0.5",
    hint: "Сводный портрет группы аудитории по её ответам.",
  },
] as const;

export type TemperatureStage = (typeof TEMPERATURE_STAGES)[number]["key"];
export type Temperatures = Record<TemperatureStage, number>;

/**
 * Диапазон, который принимает OpenAI-совместимый endpoint. Шире не бывает:
 * значение вне его провайдер отвергнет, и отказ придёт посреди оплаченного
 * прогона — после расшифровки и разбора кадров.
 */
export const TEMPERATURE_BOUNDS = { min: 0, max: 2, step: 0.1 } as const;

export const DEFAULT_TEMPERATURES: Temperatures = Object.fromEntries(
  TEMPERATURE_STAGES.map((s) => [s.key, s.default]),
) as Temperatures;

export interface TenantSettings {
  costCap: CostCapMode;
  /** Потолок вызовов модели. Осмыслен только при costCap === "hard". */
  costCapValue: number;
  whisperModel: WhisperModel;
  defaultReplication: ReplicationCount;
  temperatures: Temperatures;
}

export const DEFAULT_SETTINGS: TenantSettings = {
  costCap: "auto",
  costCapValue: 500,
  whisperModel: "large-v3",
  defaultReplication: 1,
  temperatures: DEFAULT_TEMPERATURES,
};

export const COST_CAP_BOUNDS = { min: 100, max: 5000, step: 100 } as const;

/**
 * Разбор входящего JSON. Возвращает либо настройки, либо список претензий —
 * не бросает исключение, потому что вызывающему роуту нужно ответить 400 с
 * внятным телом, а не пятисоткой.
 */
export function parseSettings(input: unknown): { ok: true; value: TenantSettings } | { ok: false; errors: string[] } {
  const errors: string[] = [];

  if (typeof input !== "object" || input === null) {
    return { ok: false, errors: ["тело запроса должно быть объектом"] };
  }
  const raw = input as Record<string, unknown>;

  const costCap = raw.costCap;
  if (!COST_CAP_MODES.includes(costCap as CostCapMode)) {
    errors.push(`costCap: ожидается ${COST_CAP_MODES.join(" | ")}`);
  }

  const costCapValue = raw.costCapValue;
  if (
    typeof costCapValue !== "number" ||
    !Number.isFinite(costCapValue) ||
    costCapValue < COST_CAP_BOUNDS.min ||
    costCapValue > COST_CAP_BOUNDS.max
  ) {
    errors.push(
      `costCapValue: число в диапазоне ${COST_CAP_BOUNDS.min}–${COST_CAP_BOUNDS.max}`,
    );
  }

  const whisperModel = raw.whisperModel;
  if (!WHISPER_MODELS.includes(whisperModel as WhisperModel)) {
    errors.push(`whisperModel: ожидается ${WHISPER_MODELS.join(" | ")}`);
  }

  const defaultReplication = raw.defaultReplication;
  if (!REPLICATION_VALUES.includes(defaultReplication as ReplicationCount)) {
    errors.push(`defaultReplication: ожидается ${REPLICATION_VALUES.join(" | ")}`);
  }

  // Температуры необязательны во входящем теле: настройки, сохранённые до
  // появления раздела, поля не содержат, и отвергать их значило бы требовать
  // от арендатора зайти в настройки прежде, чем что-либо запустить. Отсутствие
  // стадии — это её умолчание, а вот мусор в присланной стадии — отказ.
  const temperatures: Temperatures = { ...DEFAULT_TEMPERATURES };
  const rawTemperatures = raw.temperatures;
  if (rawTemperatures !== undefined) {
    if (typeof rawTemperatures !== "object" || rawTemperatures === null) {
      errors.push("temperatures: ожидается объект");
    } else {
      const provided = rawTemperatures as Record<string, unknown>;
      for (const key of Object.keys(provided)) {
        if (!TEMPERATURE_STAGES.some((s) => s.key === key)) {
          errors.push(`temperatures.${key}: неизвестная стадия`);
        }
      }
      for (const stage of TEMPERATURE_STAGES) {
        const value = provided[stage.key];
        if (value === undefined) continue;
        if (
          typeof value !== "number" ||
          !Number.isFinite(value) ||
          value < TEMPERATURE_BOUNDS.min ||
          value > TEMPERATURE_BOUNDS.max
        ) {
          errors.push(
            `temperatures.${stage.key}: число в диапазоне ` +
              `${TEMPERATURE_BOUNDS.min}–${TEMPERATURE_BOUNDS.max}`,
          );
          continue;
        }
        temperatures[stage.key] = value;
      }
    }
  }

  if (errors.length > 0) return { ok: false, errors };

  return {
    ok: true,
    value: {
      costCap: costCap as CostCapMode,
      costCapValue: costCapValue as number,
      whisperModel: whisperModel as WhisperModel,
      defaultReplication: defaultReplication as ReplicationCount,
      temperatures,
    },
  };
}

export function settingsEqual(a: TenantSettings, b: TenantSettings): boolean {
  return (
    a.costCap === b.costCap &&
    a.costCapValue === b.costCapValue &&
    a.whisperModel === b.whisperModel &&
    a.defaultReplication === b.defaultReplication &&
    TEMPERATURE_STAGES.every((s) => a.temperatures[s.key] === b.temperatures[s.key])
  );
}
