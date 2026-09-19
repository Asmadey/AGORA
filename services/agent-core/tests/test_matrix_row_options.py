"""
Матрица: у каждого вопроса внутри темы свой список вариантов и свой потолок.

─── Что здесь было не так ────────────────────────────────────────────────────
Список вариантов у матрицы был ОДИН на всё дерево. Для вопроса 9 заказчика это
верно («поднималась / не поднималась / затрудняюсь» повторяются на всех сорока
трёх подтемах), и из этого частного случая правило перенесли на матрицу вообще.

Для собственной матрицы оператора это неверно и незаметно. Он заводит тему
«Патриотизм», в ней вопрос «Гордость за страну» с вариантами «поднималась /
не поднималась» и вопрос «Что запомнилось» с вариантами «финал / музыка /
герой». Общий список склеил бы их в один: персоне на первый вопрос предложили
бы «музыку», а её ответ на второй разобрался бы против вариантов первого.

Разошлись бы при этом ЧЕТЫРЕ читателя: промпт печатает варианты, схема ответа
ограничивает выбор, расчёт долей раскладывает по вариантам, выгрузка ставит
подписи в ячейки. Каждый берёт список у ВОПРОСА, и каждый ошибётся одинаково —
то есть сверить их между собой было бы нечем, а числа получились бы правильного
вида.

Правило: варианты берутся у строки, а если своих у неё нет — у вопроса. Второе
и оставляет вопрос 9 заказчика ровно таким, каким он был.
"""

from agent_core.analytics.excel_export import _cell, _columns
from agent_core.analytics.survey_stats import survey_tally
from agent_core.survey import parse_field_answer, render_questions, row_options

#: Тема с двумя вопросами, у которых РАЗНЫЕ варианты и разный потолок выбора.
SURVEY: list[dict] = [
    {
        "id": "q-tree",
        "label": "Темы проекта",
        "type": "matrix_single",
        "block": "perception",
        "themes": [{"id": "t1", "label": "Патриотизм"}],
        "rows": [
            {
                "id": "r1",
                "label": "Гордость за страну",
                "themeId": "t1",
                "options": [
                    {"id": "r1-a", "label": "Поднималась"},
                    {"id": "r1-b", "label": "Не поднималась"},
                ],
            },
            {
                "id": "r2",
                "label": "Что запомнилось",
                "themeId": "t1",
                "maxChoices": 2,
                "options": [
                    {"id": "r2-a", "label": "Финал"},
                    {"id": "r2-b", "label": "Музыка"},
                    {"id": "r2-c", "label": "Герой"},
                ],
            },
        ],
    }
]

QUESTION = SURVEY[0]
ROW1, ROW2 = QUESTION["rows"]


def test_варианты_строки_свои_а_без_своих_общие():
    assert [o["id"] for o in row_options(QUESTION, ROW1)] == ["r1-a", "r1-b"]

    shared = {
        "id": "q9",
        "type": "matrix_single",
        "options": [{"id": "o-1", "label": "Поднималась"}],
        "rows": [{"id": "s1", "label": "Подтема"}],
    }
    assert [o["id"] for o in row_options(shared, shared["rows"][0])] == ["o-1"]


def test_промпт_печатает_варианты_каждого_вопроса():
    text = render_questions(SURVEY)

    assert "[r1-a] Поднималась" in text, "вариантов первого вопроса нет в промпте"
    assert "[r2-b] Музыка" in text, "вариантов второго вопроса нет в промпте"
    # Потолок выбора печатается у той строки, к которой относится: иначе
    # персона выберет столько, сколько захочет, и доли перестанут сходиться.
    assert "не более 2" in text


def test_ответ_разбирается_по_вариантам_своей_строки():
    assert parse_field_answer(QUESTION, "Финал", row=ROW2).option_ids == ["r2-a"]

    # «Финал» — законный вариант второго вопроса и НЕ вариант первого. Разбор
    # против общего списка принял бы его молча, и в долях первого вопроса
    # появился бы выбор, которого персоне не предлагали.
    chosen = parse_field_answer(QUESTION, "Финал", row=ROW1)
    assert chosen.error, "чужой вариант принят как свой"
    assert "не из списка" in chosen.error


def test_потолок_строки_гейтит_выбор():
    assert not parse_field_answer(QUESTION, ["Финал", "Музыка"], row=ROW2).error

    two = parse_field_answer(QUESTION, ["Поднималась", "Не поднималась"], row=ROW1)
    assert two.error, "у строки без потолка выбирается ровно один вариант"
    assert "потолок" in two.error


def test_схема_ответа_ограничивает_строку_её_вариантами():
    from agent_core.respondent.answer_schema import build_answer_model

    model = build_answer_model(SURVEY)
    fields = model.model_fields["survey_answers"].annotation.model_fields

    # Модель обязана различать строки: один общий литерал на обе означал бы,
    # что схема разрешает персоне ответить на первый вопрос вариантом второго.
    assert repr(fields["r1"].annotation) == "typing.Literal['r1-a', 'r1-b']"
    assert "r2-a" in repr(fields["r2"].annotation)
    assert "r1-a" not in repr(fields["r2"].annotation)
    # Разрешено два ответа — значит список, а не один вариант.
    assert repr(fields["r2"].annotation).startswith("list[")


def test_доли_считаются_по_вариантам_своей_строки():
    answers = [
        {
            "persona_id": "p-1",
            "survey_answers": {"r1": "Поднималась", "r2": ["Финал", "Музыка"]},
        }
    ]
    tally = survey_tally(SURVEY, answers, [{"id": "p-1"}])
    rows = tally["questions"]["q-tree"]["total"]["rows"]

    assert set(rows["r1"]["shares"]) == {"r1-a", "r1-b"}
    assert set(rows["r2"]["shares"]) == {"r2-a", "r2-b", "r2-c"}
    assert rows["r2"]["shares"]["r2-a"] == 1.0
    assert rows["r2"]["shares"]["r2-c"] == 0.0


def test_выгрузка_даёт_строке_столько_колонок_сколько_ей_разрешено():
    columns = _columns(SURVEY)
    for_r2 = [c for c in columns if c["field"] == "r2"]

    assert len(for_r2) == 2, "второй вопрос разрешает два ответа — значит две колонки"
    assert len([c for c in columns if c["field"] == "r1"]) == 1

    cell = _cell(QUESTION, ["Финал", "Музыка"], 1, row=ROW2)
    assert cell == "Музыка", "в ячейке должна стоять подпись варианта этой строки"
