/**
 * Подписи полей Persona DNA (задача #6).
 *
 * Словарь нужен ради читаемости карточки, а не ради полноты: карточка обходит
 * фактический объект DNA и рисует ВСЁ, что в нём есть. Поле, для которого здесь
 * нет подписи, всё равно попадёт на экран — с именем из схемы вместо русского
 * названия.
 *
 * Так сделано намеренно. Список, по которому строится рендер, устаревает молча:
 * добавили поле в DNA — карточка про него не знает, и никто этого не замечает.
 * Пункт cdd задачи #6 звучит как «ни одно поле не потеряно при рендере», и
 * держаться он должен на структуре обхода, а не на дисциплине того, кто правит
 * словарь.
 *
 * Имена совпадают с canonical JSON Schema (packages/shared/schemas/
 * persona-dna.schema.json) — snake_case, а не camelCase рукописного
 * agora-types.ts, который расходился со схемой и по именам, и по составу.
 */

export const CATEGORY_LABELS: Record<string, string> = {
  demographics: "Демография",
  big_five: "Большая пятёрка",
  values_and_beliefs: "Ценности и убеждения",
  viewer_behavior: "Зрительское поведение",
  communication_style: "Стиль общения",
  decision_making: "Принятие решений",
  technology_usage: "Технологии",
  lifestyle_and_interests: "Образ жизни и интересы",
};

export const FIELD_LABELS: Record<string, string> = {
  // demographics
  gender: "Пол",
  age: "Возраст",
  age_group: "Возрастная группа",
  geo: "Тип населённого пункта",
  city: "Город",
  children: "Дети",
  // big_five
  openness: "Открытость опыту",
  conscientiousness: "Добросовестность",
  extraversion: "Экстраверсия",
  agreeableness: "Доброжелательность",
  neuroticism: "Нейротизм",
  // values_and_beliefs
  // «ВЦИОМ», а не «Важные ценности»: подпись называет ИСТОЧНИК списка —
  // канонический перечень традиционных ценностей, из которого сделан выбор.
  // Число выбранных (пять) источником не продиктовано: реальный респондент
  // называл одну-две. См. data/values/traditional_values.json.
  important_values: "ВЦИОМ",
  worldview: "Мировоззрение",
  political_orientation: "Политическая ориентация",
  religious_attitude: "Отношение к религии",
  // viewer_behavior
  preferred_genres: "Любимые жанры",
  violence_tolerance: "Толерантность к насилию",
  pacing_tolerance: "Предпочитаемый темп",
  length_tolerance: "Толерантность к длине",
  franchise_loyalty: "Лояльность к франшизам",
  actor_loyalty: "Лояльность к актёрам",
  recommendation_influence: "Влияние рекомендаций",
  ideological_response: "Реакция на идеологию",
  ad_response: "Реакция на рекламу",
  production_expectations: "Ожидания от продакшена",
  attention_span: "Удержание внимания",
  // communication_style
  verbosity: "Многословность",
  directness: "Прямота",
  emotionality: "Эмоциональность",
  humor: "Юмор",
  conflict_style: "Поведение в конфликте",
  // decision_making
  style: "Стиль решений",
  risk_appetite: "Склонность к риску",
  brand_loyalty: "Лояльность к брендам",
  impulsivity: "Импульсивность",
  // technology_usage
  devices: "Устройства",
  platforms: "Платформы",
  social_media: "Соцсети",
  streaming_frequency: "Частота стриминга",
  tech_savviness: "Техническая грамотность",
  // lifestyle_and_interests
  hobbies: "Хобби",
  media_consumption: "Потребление медиа",
  social_activity: "Социальная активность",
  work_status: "Занятость",
  education_level: "Образование",
};

/**
 * Поля, значение которых — целое 1–5. Рисуются шкалой, а не числом: «4» само по
 * себе не сообщает, из скольких. Список нужен именно для формы подачи, на
 * полноту рендера он не влияет.
 */
export const SCALE_1_5 = new Set([
  "openness",
  "conscientiousness",
  "extraversion",
  "agreeableness",
  "neuroticism",
  "franchise_loyalty",
  "actor_loyalty",
  "recommendation_influence",
  "risk_appetite",
  "brand_loyalty",
  "impulsivity",
  "tech_savviness",
]);

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key;
}

export function categoryLabel(key: string): string {
  return CATEGORY_LABELS[key] ?? key;
}

/**
 * Порядок блоков карточки персоны.
 *
 * ─── Почему приоритет, а не перечень ──────────────────────────────────────
 * Карточка обходит ФАКТИЧЕСКИЙ объект DNA — это требование cdd #6: «ни одно
 * поле не потеряно при рендере». Перечень блоков это требование сломал бы:
 * поле, добавленное в схему и забытое здесь, исчезло бы с экрана молча.
 *
 * Поэтому известные блоки выстраиваются по приоритету, а всё остальное идёт
 * следом в том порядке, в каком пришло. Незнакомый блок не теряется — он
 * просто оказывается ниже.
 *
 * ─── Почему ценности первыми ──────────────────────────────────────────────
 * С 16.09.2026 их пять вместо трёх, и именно они объясняют, почему персона
 * отреагировала на материал так, а не иначе. Демография отвечает на вопрос
 * «кто это», ценности — на вопрос «почему так ответил», и второй вопрос
 * задают чаще.
 */
const CATEGORY_ORDER = [
  "values_and_beliefs",
  "demographics",
  "big_five",
  "viewer_behavior",
  "lifestyle_and_interests",
  "communication_style",
  "decision_making",
  "technology_usage",
];

export function orderCategories<T extends string>(categories: T[]): T[] {
  const rank = (c: string) => {
    const i = CATEGORY_ORDER.indexOf(c);
    // Неизвестный блок уходит в конец, но НЕ пропадает.
    return i === -1 ? CATEGORY_ORDER.length : i;
  };
  return [...categories].sort((a, b) => rank(a) - rank(b));
}
