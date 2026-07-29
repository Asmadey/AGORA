/**
 * Мок-данные для интерфейса.
 *
 * ВАЖНО: это витрина UI, а не результат работы пайплайна. Числа подобраны так,
 * чтобы соответствовать реальному grounding-корпусу (165 респондентов) — средние
 * баллы overall 7.34 / plot 7.58 / acting 8.12 / music 8.07 / cinematography 8.00
 * и распределение по возрасту с перевесом 35-44. Иначе на макетах видно одно,
 * а в проде другое, и вёрстка ломается на первых же настоящих данных.
 *
 * Заменяется реальными запросами на задачах #5 (персоны) и #20/#21 (отчёт).
 */
import type { GroupSynthesis, Persona, PersonaAnswer, StudyRun } from "./agora-types";

export const MOCK_PERSONAS: Persona[] = [
  {
    id: "p-01",
    name: "Полина Ветрова",
    generation: "Миллениалы",
    jobTitle: "Методист онлайн-школы",
    location: "Казань",
    avatarHue: 268,
    createdAt: "2026-07-24",
    personaSetId: "set-01",
    seed: 481502,
    narrative:
      "Смотрит сериалы вечером под домашние дела, звук важнее картинки. Быстро теряет доверие к истории, если герой ведёт себя непоследовательно, и почти никогда не возвращается к брошенному сериалу.",
    dna: {
      demographics: {
        gender: "жен", age: 33, ageGroup: "25-34", geo: "центры субъектов",
        city: "Казань", education: "Высшее педагогическое", occupation: "Методист",
        income: "Средний", children: "Один ребёнок 6 лет", maritalStatus: "Замужем",
      },
      bigFive: { openness: 4, conscientiousness: 4, extraversion: 3, agreeableness: 4, neuroticism: 3 },
      values: {
        coreValues: ["Семья", "Справедливость", "Профессионализм"],
        socialPriorities: ["Доступное образование", "Безопасность детей"],
        culturalOutlook: "Ценит отечественный контекст, но раздражается на展 показной пафос",
        philosophy: "Практический оптимизм: жизнь улучшается усилием, а не удачей",
        attitudeToFuture: "Осторожно позитивное, планирует горизонтом 2–3 года",
      },
      viewing: {
        favouriteGenres: ["Драма", "Детектив", "Мелодрама"],
        avoidedGenres: ["Хоррор", "Слэшер"],
        violenceTolerance: "Низкая: сцены жестокости пропускает перемоткой",
        paceTolerance: "Средняя, но провисание дольше 5 минут не прощает",
        lengthTolerance: "Серии 40–50 минут, длиннее смотрит в два захода",
        franchiseLoyalty: "Слабая, к франшизам равнодушна",
        actorLoyalty: "Высокая: идёт «на актёра», доверяет знакомым лицам",
        recommendationInfluence: "Решающая — смотрит то, что обсуждают коллеги",
        reactionToIdeology: "Резко негативная на прямолинейную повестку в любую сторону",
        reactionToAdvertising: "Терпит интеграции, если они не ломают сцену",
        productionExpectations: "Ждёт чистого звука и внятной речи актёров",
        attentionSpan: "Высокий при вовлечённости, но телефон рядом",
      },
      communication: {
        tone: "Доброжелательный, но прямой", vocabulary: "Литературный, без сленга",
        verbosity: "Развёрнуто, с примерами", humour: "Ирония, не сарказм",
        criticismStyle: "Сначала отмечает удачное, потом чётко называет проблему",
      },
      decisions: {
        riskAppetite: "Низкий", deliberation: "Взвешенная, сравнивает варианты",
        peerInfluence: "Высокое влияние близкого круга", trustInAuthority: "Умеренное, проверяет",
        priceSensitivity: "Заметная: подписки пересматривает раз в полгода",
      },
      technology: {
        devices: ["Смартфон", "Телевизор Smart TV"], platforms: ["Кинопоиск", "Иви"],
        viewingContext: "Дома вечером, часто фоном", secondScreen: "Почти всегда — мессенджеры",
      },
      lifestyle: {
        hobbies: ["Чтение", "Пешие прогулки", "Настольные игры с ребёнком"],
        dailyRhythm: "Жаворонок, свободное время после 21:00",
        socialLife: "Узкий круг, много общения по работе",
        mediaDiet: ["Telegram-каналы", "Подкасты об образовании"],
        careerPath: "Учитель → методист → руководитель направления",
      },
    },
  },
  {
    id: "p-02",
    name: "Сергей Долматов",
    generation: "Поколение X",
    jobTitle: "Инженер-наладчик",
    location: "Челябинск",
    avatarHue: 198,
    createdAt: "2026-07-24",
    personaSetId: "set-01",
    seed: 481503,
    narrative:
      "Требователен к достоверности: замечает технические ляпы и после них смотрит уже с недоверием. Ценит крепкий сюжет выше визуальных изысков.",
    dna: {
      demographics: {
        gender: "муж", age: 49, ageGroup: "45-59", geo: "центры субъектов",
        city: "Челябинск", education: "Высшее техническое", occupation: "Инженер",
        income: "Средний", children: "Двое взрослых", maritalStatus: "Женат",
      },
      bigFive: { openness: 2, conscientiousness: 5, extraversion: 2, agreeableness: 3, neuroticism: 2 },
      values: {
        coreValues: ["Порядок", "Ответственность", "Мастерство"],
        socialPriorities: ["Стабильность", "Уважение к труду"],
        culturalOutlook: "Консервативный, скептичен к экспериментам в форме",
        philosophy: "Дело важнее слов",
        attitudeToFuture: "Сдержанное, полагается на собственные силы",
      },
      viewing: {
        favouriteGenres: ["Военная драма", "Исторический", "Триллер"],
        avoidedGenres: ["Мюзикл", "Романтическая комедия"],
        violenceTolerance: "Высокая, если оправдана сюжетом",
        paceTolerance: "Высокая, готов к медленному повествованию",
        lengthTolerance: "Спокойно смотрит длинные серии",
        franchiseLoyalty: "Средняя", actorLoyalty: "Низкая, актёр вторичен",
        recommendationInfluence: "Низкая, выбирает сам",
        reactionToIdeology: "Отторжение навязанного вывода",
        reactionToAdvertising: "Раздражение на любые интеграции",
        productionExpectations: "Достоверность деталей и техники",
        attentionSpan: "Высокий, смотрит без телефона",
      },
      communication: {
        tone: "Сухой, конкретный", vocabulary: "Технический, точный",
        verbosity: "Кратко", humour: "Сдержанный сарказм",
        criticismStyle: "Называет недостаток прямо, без смягчения",
      },
      decisions: {
        riskAppetite: "Очень низкий", deliberation: "Долгая, всё проверяет",
        peerInfluence: "Минимальное", trustInAuthority: "Низкое",
        priceSensitivity: "Высокая",
      },
      technology: {
        devices: ["Телевизор", "Ноутбук"], platforms: ["Кинопоиск", "Эфирное ТВ"],
        viewingContext: "Выходные, полноценный просмотр", secondScreen: "Нет",
      },
      lifestyle: {
        hobbies: ["Гараж и автомобиль", "Рыбалка", "История техники"],
        dailyRhythm: "Ранний подъём, вечер свободен",
        socialLife: "Несколько давних друзей",
        mediaDiet: ["Новостные сайты", "YouTube про технику"],
        careerPath: "Мастер → инженер → наладчик высшей категории",
      },
    },
  },
  {
    id: "p-03",
    name: "Алина Ковач",
    generation: "Зумеры",
    jobTitle: "SMM-специалист",
    location: "Москва",
    avatarHue: 330,
    createdAt: "2026-07-24",
    personaSetId: "set-01",
    seed: 481504,
    narrative:
      "Решение смотреть дальше принимает за первые三 минуты. Клипово мыслит, но при сильном крючке досматривает залпом.",
    dna: {
      demographics: {
        gender: "жен", age: 23, ageGroup: "18-24", geo: "столицы",
        city: "Москва", education: "Незаконченное высшее", occupation: "SMM",
        income: "Ниже среднего", children: "Нет", maritalStatus: "Не замужем",
      },
      bigFive: { openness: 5, conscientiousness: 2, extraversion: 4, agreeableness: 3, neuroticism: 4 },
      values: {
        coreValues: ["Самовыражение", "Свобода выбора", "Аутентичность"],
        socialPriorities: ["Экология", "Равные возможности"],
        culturalOutlook: "Глобальный, много зарубежного контента",
        philosophy: "Жизнь как серия экспериментов",
        attitudeToFuture: "Тревожно-любопытное",
      },
      viewing: {
        favouriteGenres: ["Триллер", "Тру-крайм", "Комедия"],
        avoidedGenres: ["Производственная драма"],
        violenceTolerance: "Средняя",
        paceTolerance: "Низкая: провисание = закрыла",
        lengthTolerance: "До 30 минут, иначе на ×1.5",
        franchiseLoyalty: "Высокая к любимым вселенным",
        actorLoyalty: "Средняя, важнее «вайб»",
        recommendationInfluence: "Очень высокая — соцсети решают",
        reactionToIdeology: "Чувствительна к фальши, не к позиции",
        reactionToAdvertising: "Спокойно, если честно помечено",
        productionExpectations: "Картинка и монтаж на уровне референсов",
        attentionSpan: "Низкий без сильного крючка",
      },
      communication: {
        tone: "Эмоциональный, живой", vocabulary: "Сленг, англицизмы",
        verbosity: "Короткими репликами", humour: "Мемы и самоирония",
        criticismStyle: "Резко и сразу, без предисловий",
      },
      decisions: {
        riskAppetite: "Высокий", deliberation: "Импульсивная",
        peerInfluence: "Очень высокое", trustInAuthority: "Низкое",
        priceSensitivity: "Высокая, делит подписки с друзьями",
      },
      technology: {
        devices: ["Смартфон"], platforms: ["Кинопоиск", "YouTube", "Telegram"],
        viewingContext: "В транспорте и перед сном", secondScreen: "Всегда",
      },
      lifestyle: {
        hobbies: ["Фотография", "Концерты", "Бег"],
        dailyRhythm: "Сова", socialLife: "Широкий круг, много активностей",
        mediaDiet: ["TikTok", "Telegram", "Подкасты"],
        careerPath: "Стажёр → SMM-специалист",
      },
    },
  },
  {
    id: "p-04",
    name: "Марина Гущина",
    generation: "Поколение X",
    jobTitle: "Главный бухгалтер",
    location: "Нижний Новгород",
    avatarHue: 24,
    createdAt: "2026-07-24",
    personaSetId: "set-01",
    seed: 481505,
    narrative:
      "Смотрит ради героев, а не ради сюжета. Прощает предсказуемость, но не прощает неубедительных мотиваций.",
    dna: {
      demographics: {
        gender: "жен", age: 41, ageGroup: "35-44", geo: "центры субъектов",
        city: "Нижний Новгород", education: "Высшее экономическое", occupation: "Бухгалтер",
        income: "Выше среднего", children: "Двое школьников", maritalStatus: "Замужем",
      },
      bigFive: { openness: 3, conscientiousness: 5, extraversion: 3, agreeableness: 4, neuroticism: 3 },
      values: {
        coreValues: ["Семья", "Надёжность", "Достаток"],
        socialPriorities: ["Здравоохранение", "Образование детей"],
        culturalOutlook: "Умеренно традиционный",
        philosophy: "Всё должно быть по-честному",
        attitudeToFuture: "Спокойное, с финансовой подушкой",
      },
      viewing: {
        favouriteGenres: ["Мелодрама", "Семейная сага", "Детектив"],
        avoidedGenres: ["Артхаус", "Хоррор"],
        violenceTolerance: "Низкая",
        paceTolerance: "Высокая, любит неспешные истории",
        lengthTolerance: "Длинные сезоны — плюс",
        franchiseLoyalty: "Средняя", actorLoyalty: "Очень высокая",
        recommendationInfluence: "Высокая, от подруг и коллег",
        reactionToIdeology: "Нейтральная, если не в лоб",
        reactionToAdvertising: "Спокойная",
        productionExpectations: "Красивая картинка, узнаваемая натура",
        attentionSpan: "Средний, смотрит вечерами",
      },
      communication: {
        tone: "Тёплый", vocabulary: "Разговорный литературный",
        verbosity: "Подробно", humour: "Мягкий",
        criticismStyle: "Смягчает, но позицию держит",
      },
      decisions: {
        riskAppetite: "Низкий", deliberation: "Основательная",
        peerInfluence: "Среднее", trustInAuthority: "Высокое",
        priceSensitivity: "Средняя",
      },
      technology: {
        devices: ["Smart TV", "Планшет"], platforms: ["Иви", "Кинопоиск"],
        viewingContext: "Вечер с семьёй", secondScreen: "Иногда",
      },
      lifestyle: {
        hobbies: ["Дача", "Кулинария", "Сериалы"],
        dailyRhythm: "Плотный график до 19:00",
        socialLife: "Семья и коллеги",
        mediaDiet: ["Телевидение", "WhatsApp-рассылки"],
        careerPath: "Бухгалтер → главный бухгалтер",
      },
    },
  },
  {
    id: "p-05",
    name: "Тимур Аскеров",
    generation: "Миллениалы",
    jobTitle: "Продакт-менеджер",
    location: "Санкт-Петербург",
    avatarHue: 152,
    createdAt: "2026-07-24",
    personaSetId: "set-01",
    seed: 481506,
    narrative:
      "Анализирует структуру повествования почти профессионально. Хвалит скупо, но обосновывает каждое замечание конкретной сценой.",
    dna: {
      demographics: {
        gender: "муж", age: 36, ageGroup: "35-44", geo: "столицы",
        city: "Санкт-Петербург", education: "Высшее техническое", occupation: "Продакт-менеджер",
        income: "Высокий", children: "Один ребёнок 3 года", maritalStatus: "Женат",
      },
      bigFive: { openness: 5, conscientiousness: 4, extraversion: 3, agreeableness: 2, neuroticism: 2 },
      values: {
        coreValues: ["Развитие", "Рациональность", "Автономия"],
        socialPriorities: ["Технологический прогресс", "Городская среда"],
        culturalOutlook: "Космополитичный",
        philosophy: "Всё можно улучшить итерацией",
        attitudeToFuture: "Уверенное",
      },
      viewing: {
        favouriteGenres: ["Научная фантастика", "Психологический триллер", "Док"],
        avoidedGenres: ["Мелодрама"],
        violenceTolerance: "Высокая при осмысленности",
        paceTolerance: "Средняя, ценит плотность событий",
        lengthTolerance: "Мини-сериалы предпочтительнее длинных сезонов",
        franchiseLoyalty: "Низкая", actorLoyalty: "Низкая",
        recommendationInfluence: "Средняя, доверяет узкому кругу и рейтингам",
        reactionToIdeology: "Замечает и отмечает вслух",
        reactionToAdvertising: "Негативная",
        productionExpectations: "Высокие: сравнивает с международными образцами",
        attentionSpan: "Высокий",
      },
      communication: {
        tone: "Аналитический", vocabulary: "Профессиональный, термины",
        verbosity: "Структурно, по пунктам", humour: "Сухой",
        criticismStyle: "Разбирает по частям, предлагает решение",
      },
      decisions: {
        riskAppetite: "Средний", deliberation: "Быстрая на данных",
        peerInfluence: "Низкое", trustInAuthority: "Низкое",
        priceSensitivity: "Низкая",
      },
      technology: {
        devices: ["Ноутбук", "Проектор", "Смартфон"], platforms: ["Кинопоиск", "Зарубежные сервисы"],
        viewingContext: "Поздний вечер, сфокусированно", secondScreen: "Редко",
      },
      lifestyle: {
        hobbies: ["Велосипед", "Настольные игры", "Кофе"],
        dailyRhythm: "Сова", socialLife: "Профессиональное сообщество",
        mediaDiet: ["Подкасты", "Отраслевые рассылки"],
        careerPath: "Аналитик → продакт → руководитель продукта",
      },
    },
  },
  {
    id: "p-06",
    name: "Галина Прохорова",
    generation: "Бумеры",
    jobTitle: "Библиотекарь на пенсии",
    location: "Воронеж",
    avatarHue: 42,
    createdAt: "2026-07-24",
    personaSetId: "set-01",
    seed: 481507,
    narrative:
      "Оценивает через язык и литературность диалогов. К жестокости непримирима — одна сцена может закрыть для неё весь сериал.",
    dna: {
      demographics: {
        gender: "жен", age: 63, ageGroup: "60+", geo: "центры субъектов",
        city: "Воронеж", education: "Высшее гуманитарное", occupation: "Пенсионер",
        income: "Низкий", children: "Взрослые дети, внуки", maritalStatus: "Вдова",
      },
      bigFive: { openness: 3, conscientiousness: 5, extraversion: 2, agreeableness: 5, neuroticism: 3 },
      values: {
        coreValues: ["Культура", "Достоинство", "Память"],
        socialPriorities: ["Поддержка пожилых", "Сохранение наследия"],
        culturalOutlook: "Традиционный, литературоцентричный",
        philosophy: "Слово формирует человека",
        attitudeToFuture: "Настороженное",
      },
      viewing: {
        favouriteGenres: ["Экранизации классики", "Историческая драма"],
        avoidedGenres: ["Боевик", "Хоррор", "Триллер"],
        violenceTolerance: "Крайне низкая",
        paceTolerance: "Очень высокая",
        lengthTolerance: "Любая",
        franchiseLoyalty: "Отсутствует", actorLoyalty: "Высокая к театральной школе",
        recommendationInfluence: "Средняя, от телевидения и знакомых",
        reactionToIdeology: "Болезненная на искажение истории",
        reactionToAdvertising: "Терпимая",
        productionExpectations: "Достоверность костюмов и речи",
        attentionSpan: "Очень высокий",
      },
      communication: {
        tone: "Вежливый, обстоятельный", vocabulary: "Богатый, литературный",
        verbosity: "Развёрнуто", humour: "Тонкий",
        criticismStyle: "Мягко по форме, твёрдо по сути",
      },
      decisions: {
        riskAppetite: "Очень низкий", deliberation: "Долгая",
        peerInfluence: "Среднее", trustInAuthority: "Высокое",
        priceSensitivity: "Очень высокая",
      },
      technology: {
        devices: ["Телевизор"], platforms: ["Эфирное ТВ", "Иви"],
        viewingContext: "День и вечер", secondScreen: "Нет",
      },
      lifestyle: {
        hobbies: ["Чтение", "Внуки", "Сад"],
        dailyRhythm: "Ранний", socialLife: "Соседи и семья",
        mediaDiet: ["Телевидение", "Печатная пресса"],
        careerPath: "Библиотекарь 38 лет",
      },
    },
  },
];

const answer = (
  personaId: string,
  scores: [number, number, number, number, number],
  watchedUntil: number,
  wouldRecommend: boolean,
  emotions: string[],
  verbatim: string,
  refs: { timecode: string; note: string }[],
  qaFlags: string[] = [],
): PersonaAnswer => ({
  personaId,
  scores: {
    overall_impression: scores[0], plot: scores[1], acting: scores[2],
    music: scores[3], cinematography: scores[4],
  },
  wouldRecommend,
  watchedUntil,
  emotions,
  verbatim,
  groundingRefs: refs,
  qaFlags,
});

export const MOCK_ANSWERS: PersonaAnswer[] = [
  answer("p-01", [7, 6, 8, 8, 8], 78, false, ["Интерес", "Разочарование"],
    "До четырнадцатой минуты держало, а потом героиня поступает так, как живой человек в её положении не поступит. Дальше я уже смотрела вполуха.",
    [{ timecode: "14:05", note: "решение героини уйти из дома" }, { timecode: "03:20", note: "сильная завязка" }]),
  answer("p-02", [8, 8, 8, 7, 9], 100, true, ["Уважение", "Сосредоточенность"],
    "Крепко сделано. Матчасть не хромает, что редкость. Музыка местами лишняя — там, где и без неё всё понятно.",
    [{ timecode: "22:40", note: "сцена на производстве" }, { timecode: "31:10", note: "избыточная музыкальная подложка" }]),
  answer("p-03", [6, 6, 8, 9, 8], 42, false, ["Скука", "Раздражение"],
    "Первые минуты норм, дальше провисает. Я на середине уже листала телефон. Саундтрек топ, но этого мало.",
    [{ timecode: "09:15", note: "затянутый диалог" }],
    ["low_engagement"]),
  answer("p-04", [8, 8, 9, 8, 8], 100, true, ["Сопереживание", "Тепло"],
    "Актёры вытягивают всё. Мать веришь безоговорочно — вот за ней и следишь, даже когда сюжет предсказуем.",
    [{ timecode: "18:30", note: "сцена объяснения с сыном" }]),
  answer("p-05", [7, 7, 8, 8, 8], 100, false, ["Интерес", "Скепсис"],
    "Структурно вторая треть провисает: две сюжетные линии дублируют функцию. Операторская работа сильно выше среднего.",
    [{ timecode: "16:00", note: "дублирование линий" }, { timecode: "27:45", note: "длинный план без склейки" }]),
  answer("p-06", [7, 8, 9, 8, 8], 64, false, ["Тревога", "Печаль"],
    "Язык живой, диалоги не картонные. Но сцена в третьем акте — я такое смотреть не могу, выключила и не вернулась.",
    [{ timecode: "34:20", note: "сцена насилия" }, { timecode: "11:00", note: "диалог у окна" }]),
];

export const MOCK_SYNTHESIS: GroupSynthesis = {
  themes: [
    {
      title: "Актёрская игра вытягивает материал",
      agreement: "согласие",
      summary:
        "Все шесть персон ставят актёрам выше, чем сюжету. Разрыв в 0.7 балла устойчив по всем сегментам — это самая сильная сторона материала.",
      quotes: [
        { persona: "Марина, 41", text: "Актёры вытягивают всё. Матери веришь безоговорочно.", timecode: "18:30" },
        { persona: "Галина, 63", text: "Диалоги не картонные.", timecode: "11:00" },
      ],
    },
    {
      title: "Провал вовлечения во второй трети",
      agreement: "согласие",
      summary:
        "Четыре персоны независимо указали на отрезок 09:00–16:00 как на провисание. Двое из них после него снизили внимание и не восстановили его до конца.",
      quotes: [
        { persona: "Алина, 23", text: "На середине я уже листала телефон.", timecode: "09:15" },
        { persona: "Тимур, 36", text: "Две сюжетные линии дублируют функцию.", timecode: "16:00" },
      ],
    },
    {
      title: "Сцена насилия в третьем акте раскалывает аудиторию",
      agreement: "раскол",
      summary:
        "Сегмент 45+ реагирует резко негативно вплоть до прекращения просмотра, младшие сегменты воспринимают сцену как оправданную. Это не вопрос вкуса — это разная граница допустимого.",
      quotes: [
        { persona: "Галина, 63", text: "Я такое смотреть не могу, выключила.", timecode: "34:20" },
        { persona: "Сергей, 49", text: "Оправдано сюжетом, вопросов нет.", timecode: "34:20" },
      ],
    },
  ],
  strengths: [
    "Актёрский ансамбль — самый высокий балл по всем сегментам (8.3)",
    "Операторская работа держит уровень международных образцов",
    "Завязка удерживает внимание первые 8 минут у всех персон",
  ],
  weaknesses: [
    "Провисание 09:00–16:00: дублирование сюжетных линий",
    "Мотивация героини на 14:05 не читается как достоверная",
    "Сцена 34:20 теряет сегмент 45+ безвозвратно",
  ],
};

export const MOCK_STUDY: StudyRun = {
  id: "task-8f21",
  projectName: "Сериал «Ландыши», сезон 2",
  contentTitle: "Серия 1, черновой монтаж",
  mode: "short",
  durationSec: 2640,
  audienceSize: 6,
  replicationCount: 3,
  status: "REPORT_READY",
  createdAt: "2026-07-26T18:40:00+03:00",
  narrative: [
    "Материал получает 7.2 из 10 в среднем по аудитории — это на уровне референсных значений корпуса, но с заметным расслоением по сегментам.",
    "Главный актив — актёрская игра (8.3). Она стабильно выше сюжета на 0.7 балла у каждой без исключения персоны, то есть материал держится на исполнении, а не на структуре.",
    "Главный риск — не средний балл, а два конкретных места. Отрезок 09:00–16:00 теряет вовлечённость у четырёх персон из шести, а сцена 34:20 необратимо отсекает сегмент 45+: обе персоны этого сегмента прекратили просмотр и не вернулись.",
    "Практический вывод: перемонтаж второй трети даёт больше, чем любая доработка финала, потому что до финала часть аудитории просто не доходит.",
  ],
  aggregate: {
    scores: {
      overall_impression: 7.2, plot: 7.2, acting: 8.3, music: 8.0, cinematography: 8.2,
    },
    confidence: {
      overall_impression: { mean: 7.2, min: 6.0, max: 8.0, stdev: 0.75 },
      plot: { mean: 7.2, min: 6.0, max: 8.0, stdev: 0.98 },
      acting: { mean: 8.3, min: 8.0, max: 9.0, stdev: 0.52 },
      music: { mean: 8.0, min: 7.0, max: 9.0, stdev: 0.63 },
      cinematography: { mean: 8.2, min: 8.0, max: 9.0, stdev: 0.41 },
    },
    nps: -33,
    retentionRate: 80.7,
    emotionalIndex: 6.4,
    topEmotions: [
      { name: "Интерес", pct: 33 },
      { name: "Сопереживание", pct: 17 },
      { name: "Разочарование", pct: 17 },
      { name: "Скепсис", pct: 17 },
      { name: "Тревога", pct: 16 },
    ],
    segments: [
      {
        segment: "45+",
        scores: { overall_impression: 7.5, plot: 8.0, acting: 8.5, music: 7.5, cinematography: 8.5 },
        note: "Высокие баллы, но самый низкий досмотр: сцена 34:20 обрывает просмотр",
      },
      {
        segment: "25-44",
        scores: { overall_impression: 7.3, plot: 7.0, acting: 8.3, music: 8.0, cinematography: 8.0 },
        note: "Ядро аудитории, критика сосредоточена на мотивациях героев",
      },
      {
        segment: "18-24",
        scores: { overall_impression: 6.0, plot: 6.0, acting: 8.0, music: 9.0, cinematography: 8.0 },
        note: "Самый низкий досмотр по темпу — 42%",
      },
    ],
  },
  synthesis: MOCK_SYNTHESIS,
  answers: MOCK_ANSWERS,
};

export const MOCK_RUNS: StudyRun[] = [
  MOCK_STUDY,
  {
    id: "task-7c04",
    projectName: "Сериал «Ландыши», сезон 2",
    contentTitle: "Серия 1, первая сборка",
    mode: "short",
    durationSec: 2580,
    audienceSize: 6,
    replicationCount: 1,
    status: "REPORT_READY",
    createdAt: "2026-07-21T12:10:00+03:00",
  },
  {
    id: "task-9a55",
    projectName: "Промо-ролик «Константинополь»",
    contentTitle: "Тизер 60 сек",
    mode: "short",
    durationSec: 60,
    audienceSize: 20,
    replicationCount: 1,
    status: "RUNNING",
    createdAt: "2026-07-27T09:05:00+03:00",
  },
];
