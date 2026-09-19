import {
  SurveyBarChart,
  SurveyDonutChart,
  SurveyMatrixChart,
  SurveyMetricCard,
  SurveyNpsChart,
  SurveyScaleChart,
  SurveyStackedBarChart,
} from "@/components/agora/survey-charts";

// Маршрут намеренно нигде не линкуется: это визуальный стенд примитивов для проверки до подключения отчёта.
export default function SurveyChartsDevPage() {
  const sample = { answered: 184, surveyed: 200, excluded: 16 };

  return (
    <main className="min-h-screen max-w-full overflow-x-hidden bg-background px-4 py-8 text-foreground sm:px-6">
      <div className="mx-auto max-w-5xl">
        <p className="text-xs uppercase tracking-[0.16em] text-slate">AGORA · survey chart primitives</p>
        <h1 className="mt-2 break-words text-2xl font-bold">Визуальный стенд графиков отчёта</h1>
        <p className="mt-2 max-w-2xl break-words text-sm leading-relaxed text-slate">
          Все значения выдуманы. Здесь специально оставлены ноль, отсутствие ответа,
          подавленный срез, длинный вопрос и кольцо с неполной арифметикой.
        </p>

        <div className="mt-6 grid min-w-0 gap-4 lg:grid-cols-2">
          <SurveyScaleChart
            title="Насколько вам в целом понравился этот ролик и захотелось ли посмотреть его ещё раз после просмотра?"
            mean={8.2}
            min={0}
            max={10}
            topBox={0.61}
            minLabel="совсем не понравился"
            maxLabel="очень понравился"
            target={{ mean: 8.1, topBox: 0.58, n: 76 }}
            sample={sample}
          />

          <SurveyDonutChart
            title="Какие эмоции оставил у вас материал?"
            parts={[
              { id: "good", label: "Произвёл хорошее впечатление", tone: "positive-soft", share: 0.65 },
              { id: "neutral", label: "Оставил равнодушным", tone: "neutral", share: 0.2 },
              { id: "bad", label: "Разочаровал", tone: "negative-soft", share: 0.55 },
            ]}
            center={{ share: 0.65, caption: "положительные эмоции" }}
            secondary={{ share: null, caption: "второй показатель" }}
            target={{
              n: 12,
              belowThreshold: true,
              parts: [
                { id: "good", label: "Произвёл хорошее впечатление", tone: "positive-soft", share: 0.7 },
                { id: "neutral", label: "Оставил равнодушным", tone: "neutral", share: 0.1 },
                { id: "bad", label: "Разочаровал", tone: "negative-soft", share: 0.2 },
              ],
            }}
            sample={sample}
          />

          <SurveyBarChart
            title="Какие ценности вы увидели в ролике?"
            note="Можно выбрать до трёх вариантов. Длина столбика показывает сравнение долей, а число - долю ответивших."
            rows={[
              { id: "family", label: "Семья и близкие", share: 0.74 },
              { id: "zero", label: "Нулевая доля", share: 0 },
              { id: "missing", label: "Нет ответа", share: null },
              { id: "legacy", label: "option_legacy_07", share: 0.19, tone: "key" },
            ]}
            target={{
              n: 67,
              rows: [
                { id: "family", share: 0.6 },
                { id: "zero", share: 0 },
                { id: "missing", share: null },
                { id: "legacy", share: 0.14 },
              ],
            }}
            sample={sample}
          />

          <SurveyStackedBarChart
            title="Насколько материал вызвал доверие?"
            parts={[
              { id: "negative", label: "Скорее нет", tone: "negative", share: 0.18, side: "negative" },
              { id: "neutral", label: "Затрудняюсь ответить", tone: "unknown", share: 0.12, side: "service" },
              { id: "positive", label: "Скорее да", tone: "positive", share: 0.55, side: "positive" },
            ]}
            target={{
              n: 63,
              parts: [
                { id: "negative", label: "Скорее нет", tone: "negative", share: 0.2 },
                { id: "neutral", label: "Затрудняюсь ответить", tone: "unknown", share: 0.1 },
                { id: "positive", label: "Скорее да", tone: "positive", share: 0.6 },
              ],
            }}
            sample={sample}
          />

          <SurveyMatrixChart
            title="Оценка отдельных характеристик материала"
            groups={[
              {
                id: "message",
                title: "Сообщение и польза",
                rows: [
                  {
                    id: "clear",
                    label: "Сообщение понятно",
                    parts: [
                      { id: "no", label: "Нет", tone: "negative", share: 0.1 },
                      { id: "unsure", label: "Затрудняюсь ответить", tone: "unknown", share: 0.15 },
                      { id: "yes", label: "Да", tone: "positive", share: 0.65 },
                    ],
                    target: { n: 68, count: 4, share: 0.91 },
                  },
                ],
              },
              {
                id: "story",
                title: "История и герои",
                rows: [
                  {
                    id: "hero",
                    label: "Герой вызывает симпатию",
                    parts: [
                      { id: "no", label: "Нет", tone: "negative", share: 0.08 },
                      { id: "unsure", label: "Затрудняюсь ответить", tone: "unknown", share: 0.2 },
                      { id: "yes", label: "Да", tone: "positive", share: 0.63 },
                    ],
                    target: { n: 9, count: null, share: null, belowThreshold: true },
                  },
                ],
              },
            ]}
            sample={sample}
          />

          <SurveyNpsChart
            title="Насколько вероятно, что вы порекомендуете этот бренд?"
            values={{ promoters: 0.64, neutral: 0.27, detractors: 0.09 }}
            target={{
              n: 72,
              values: { promoters: 0.7, neutral: 0.2, detractors: 0.1 },
            }}
            sample={sample}
          />

          <SurveyMetricCard
            title="Общее эмоциональное впечатление"
            value={0.74}
            caption="испытали только положительные эмоции"
            target={{ value: 0.6, n: 71 }}
            sample={sample}
          />
        </div>
      </div>
    </main>
  );
}
