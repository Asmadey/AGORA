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

/**
 * Модели транскрипции — ровно те, что лежат в образе воркера.
 *
 * `large-v3-turbo` убран: его в кэше нет, и выбор уводил прогон качать веса уже
 * после заливки ролика. Список закреплён тестом вместе с перечнем воркера —
 * два списка в двух языках расходятся молча.
 */
export const WHISPER_MODELS = ["large-v3"] as const;
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

/**
 * ─── Выбор моделей ─────────────────────────────────────────────────────────
 *
 * Три роли, а не одна. Разбор кадра идёт в модель ЗРЕНИЯ, и текстовая модель
 * картинку не примет: один общий селектор сломал бы разбор кадров молча —
 * прогон дошёл бы до него после расшифровки и упал бы на каждой панели.
 *
 * Судья вынесен отдельно намеренно: его задача — не соглашаться с проверяемым,
 * и одна модель в обеих ролях склонна признавать собственную работу верной.
 * Пустая строка означает «та же, что текстовая» — это законный режим и
 * умолчание, потому что второй агент есть не у всех.
 */
export interface ModelSelection {
  text: string;
  vision: string;
  /** "" — судить той же моделью, что отвечает. */
  judge: string;
}

/** Усилия рассуждения. Значения — те, что понимает `chat_template_kwargs`. */
export const REASONING_EFFORTS = ["low", "medium", "high", "max"] as const;
export type ReasoningEffort = (typeof REASONING_EFFORTS)[number];

export interface Reasoning {
  /**
   * Размышление перед ответом.
   *
   * Уезжает ключом `enable_thinking`, а не `thinking`: замер на боевом ключе
   * 17.08.2026 показал, что `thinking: false` шлюз ИГНОРИРУЕТ — 480 токенов
   * вывода против 4 при `enable_thinking: false`. Ключ из документации
   * провайдера здесь не работает, и переключатель, повешенный на него, был бы
   * ручкой, которая ничего не крутит.
   */
  thinking: boolean;
  /**
   * Текущий endpoint этот параметр ИГНОРИРУЕТ — замер там же: с
   * `enable_thinking: false` результат одинаков при `max` и без параметра
   * вовсе. Поле хранится и отправляется, чтобы заработать само при смене
   * провайдера, и подписано в интерфейсе честно.
   */
  effort: ReasoningEffort;
}

export interface TenantSettings {
  costCap: CostCapMode;
  /** Потолок вызовов модели. Осмыслен только при costCap === "hard". */
  costCapValue: number;
  whisperModel: WhisperModel;
  defaultReplication: ReplicationCount;
  temperatures: Temperatures;
  models: ModelSelection;
  reasoning: Reasoning;
  /** Рассуждение судьи — отдельно от основного: у проверки другая цена ошибки. */
  judgeReasoning: Reasoning;
  /** Адрес провайдера. Пустая строка — брать из окружения сервера. */
  endpoint: string;
  /**
   * Маска действующего ключа — только для показа. Приходит с сервера, обратно
   * не принимается: сам ключ отправляется отдельным полем `apiKey` и наружу не
   * возвращается никогда.
   */
  apiKeyMask: string;
}

export const DEFAULT_MODELS: ModelSelection = { text: "", vision: "", judge: "" };
export const DEFAULT_REASONING: Reasoning = { thinking: false, effort: "max" };

export const DEFAULT_SETTINGS: TenantSettings = {
  costCap: "auto",
  costCapValue: 500,
  whisperModel: "large-v3",
  defaultReplication: 1,
  temperatures: DEFAULT_TEMPERATURES,
  // Пустые строки означают «как задано в окружении сервера». Подставлять сюда
  // конкретные имена нельзя: они разъедутся с .env при первой же смене, и
  // интерфейс станет показывать модель, по которой прогон не идёт.
  models: DEFAULT_MODELS,
  reasoning: DEFAULT_REASONING,
  judgeReasoning: DEFAULT_REASONING,
  endpoint: "",
  apiKeyMask: "не задан",
};

export const COST_CAP_BOUNDS = { min: 100, max: 5000, step: 100 } as const;

/**
 * Похоже на хост: точка есть, пробелов и `@` нет.
 *
 * `@` исключён намеренно — это признак почты или пары «логин:пароль», а не
 * адреса сервиса. Дописать к такой строке схему значит превратить чужое
 * значение в правдоподобный endpoint.
 */
const HOSTISH = /^[\w-]+(\.[\w-]+)+(:\d+)?(\/\S*)?$/;

export type EndpointCheck = { ok: true; value: string } | { ok: false; error: string };

/**
 * Адрес провайдера в пригодном для записи виде — либо внятная претензия.
 *
 * Одна функция на две стороны: интерфейс показывает претензию у поля, сервер
 * защищает базу. Две отдельные проверки разошлись бы, и разошлись бы молча —
 * экран разрешал бы то, что роут потом отвергает, и наоборот.
 *
 * ─── Что здесь чинится, а что нет ────────────────────────────────────────────
 * Чинится форма записи: снимаются кавычки (значение переезжает из `.env.local`
 * вместе с ними — CLAUDE.md §9) и дописывается схема, если её забыли. Человек,
 * скопировавший `foundation-models.api.cloud.ru/v1` из документации
 * провайдера, сообщил ровно то, что требовалось.
 *
 * Не чинится смысл: строка, не похожая на хост, отвергается. Пустое значение
 * законно и означает «брать из окружения сервера» — это и есть значение по
 * умолчанию.
 */
export function normalizeEndpoint(input: string): EndpointCheck {
  let text = String(input ?? "").trim();

  // Кавычки снимаются только парные — одиночная где-то внутри строки означает
  // опечатку, и молча её проглатывать не за чем.
  const quoted = /^(["'])(.*)\1$/.exec(text);
  if (quoted) text = quoted[2].trim();

  if (!text) return { ok: true, value: "" };
  if (/^https?:\/\/\S+$/.test(text)) return { ok: true, value: text };
  if (HOSTISH.test(text)) return { ok: true, value: `https://${text}` };

  return {
    ok: false,
    // Само значение в текст ошибки не попадает: в поле могло оказаться то, чего
    // человек туда не писал, — вплоть до логина из менеджера паролей, — а текст
    // ошибки уезжает в ответ и в логи (CLAUDE.md §7).
    error: "ожидается http(s)-адрес либо пусто",
  };
}

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

  // ─── Модели и рассуждение ─────────────────────────────────────────────────
  //
  // Имена моделей не сверяются со списком: список живой, его отдаёт провайдер,
  // и зашитый перечень устарел бы молча — ровно так уже вышло с моделями
  // Whisper, где интерфейс предлагал две, а в образе лежала одна. Проверяется
  // только форма: строка разумной длины без пробелов по краям.
  const models: ModelSelection = { ...DEFAULT_MODELS };
  const rawModels = raw.models;
  if (rawModels !== undefined) {
    if (typeof rawModels !== "object" || rawModels === null) {
      errors.push("models: ожидается объект");
    } else {
      for (const role of ["text", "vision", "judge"] as const) {
        const value = (rawModels as Record<string, unknown>)[role];
        if (value === undefined) continue;
        if (typeof value !== "string" || value.length > 200) {
          errors.push(`models.${role}: строка не длиннее 200 символов`);
          continue;
        }
        models[role] = value.trim();
      }
    }
  }

  function parseReasoning(source: unknown, field: string): Reasoning {
    const out: Reasoning = { ...DEFAULT_REASONING };
    if (source === undefined) return out;
    if (typeof source !== "object" || source === null) {
      errors.push(`${field}: ожидается объект`);
      return out;
    }
    const r = source as Record<string, unknown>;
    if (r.thinking !== undefined) {
      if (typeof r.thinking !== "boolean") errors.push(`${field}.thinking: ожидается true или false`);
      else out.thinking = r.thinking;
    }
    if (r.effort !== undefined) {
      if (!REASONING_EFFORTS.includes(r.effort as ReasoningEffort)) {
        errors.push(`${field}.effort: ожидается ${REASONING_EFFORTS.join(" | ")}`);
      } else out.effort = r.effort as ReasoningEffort;
    }
    return out;
  }

  const reasoning = parseReasoning(raw.reasoning, "reasoning");
  const judgeReasoning = parseReasoning(raw.judgeReasoning, "judgeReasoning");

  let endpoint = "";
  if (raw.endpoint !== undefined) {
    if (typeof raw.endpoint !== "string" || raw.endpoint.length > 500) {
      errors.push("endpoint: строка не длиннее 500 символов");
    } else {
      const normalized = normalizeEndpoint(raw.endpoint);
      if (normalized.ok) endpoint = normalized.value;
      else errors.push(`endpoint: ${normalized.error}`);
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
      models,
      reasoning,
      judgeReasoning,
      endpoint,
      // Маска приходит с сервера и на вход не принимается: сам ключ едет
      // отдельным полем `apiKey`, а обратно не возвращается никогда.
      apiKeyMask: "",
    },
  };
}

function reasoningEqual(a: Reasoning, b: Reasoning): boolean {
  return a.thinking === b.thinking && a.effort === b.effort;
}

export function settingsEqual(a: TenantSettings, b: TenantSettings): boolean {
  return (
    a.costCap === b.costCap &&
    a.costCapValue === b.costCapValue &&
    a.whisperModel === b.whisperModel &&
    a.defaultReplication === b.defaultReplication &&
    a.endpoint === b.endpoint &&
    a.models.text === b.models.text &&
    a.models.vision === b.models.vision &&
    a.models.judge === b.models.judge &&
    reasoningEqual(a.reasoning, b.reasoning) &&
    reasoningEqual(a.judgeReasoning, b.judgeReasoning) &&
    TEMPERATURE_STAGES.every((s) => a.temperatures[s.key] === b.temperatures[s.key])
  );
}
