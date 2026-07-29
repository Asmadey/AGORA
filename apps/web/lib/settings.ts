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

export interface TenantSettings {
  costCap: CostCapMode;
  /** Потолок вызовов модели. Осмыслен только при costCap === "hard". */
  costCapValue: number;
  whisperModel: WhisperModel;
  defaultReplication: ReplicationCount;
}

export const DEFAULT_SETTINGS: TenantSettings = {
  costCap: "auto",
  costCapValue: 500,
  whisperModel: "large-v3",
  defaultReplication: 1,
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

  if (errors.length > 0) return { ok: false, errors };

  return {
    ok: true,
    value: {
      costCap: costCap as CostCapMode,
      costCapValue: costCapValue as number,
      whisperModel: whisperModel as WhisperModel,
      defaultReplication: defaultReplication as ReplicationCount,
    },
  };
}

export function settingsEqual(a: TenantSettings, b: TenantSettings): boolean {
  return (
    a.costCap === b.costCap &&
    a.costCapValue === b.costCapValue &&
    a.whisperModel === b.whisperModel &&
    a.defaultReplication === b.defaultReplication
  );
}
