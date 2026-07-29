import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, MessageCircle } from "lucide-react";
import { BigFiveChart, Chip, Field, TimecodeRef } from "@/components/agora/Primitives";
import { MOCK_ANSWERS, MOCK_PERSONAS, MOCK_STUDY } from "@/lib/mock-data";
import { CRITERIA, CRITERIA_LABELS } from "@/lib/agora-types";

/**
 * Полная карточка персоны.
 *
 * Ключевое требование (задача #6): здесь показаны ВСЕ атрибуты DNA, а не парадное
 * подмножество. Смысл продукта — что персона не выдумана на ходу, а имеет
 * задокументированный профиль; если карточка показывает восемь полей из пятидесяти,
 * проверить это утверждение невозможно.
 */

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5">
      <h2 className="text-sm font-semibold">{title}</h2>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export default async function PersonaCardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const persona = MOCK_PERSONAS.find((p) => p.id === id);
  // notFound() возвращает never, но полагаться на это ради корректности остального
  // кода не стоит: явный return делает сужение типа независимым от сигнатуры Next.
  if (!persona) {
    notFound();
    return null;
  }

  const { dna } = persona;
  const answer = MOCK_ANSWERS.find((a) => a.personaId === persona.id);

  return (
    <div className="mx-auto max-w-5xl p-8">
      <Link
        href="/personas"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Все персоны
      </Link>

      {/* Шапка */}
      <div className="flex flex-wrap items-start gap-5">
        <div
          className="grid h-16 w-16 shrink-0 place-items-center rounded-full text-lg font-semibold"
          style={{
            backgroundColor: `hsl(${persona.avatarHue} 45% 22%)`,
            color: `hsl(${persona.avatarHue} 70% 78%)`,
          }}
        >
          {persona.name.split(" ").map((w) => w[0]).join("")}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">{persona.name}</h1>
          <p className="mt-0.5 text-muted-foreground">
            {persona.jobTitle} · {persona.location}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Chip>{persona.generation}</Chip>
            <Chip tone="outline">{dna.demographics.age} лет</Chip>
            <Chip tone="outline">{dna.demographics.geo}</Chip>
            <Chip tone="outline">seed {persona.seed}</Chip>
          </div>
        </div>
        <Link
          href={`/runs/${MOCK_STUDY.id}/chat?persona=${persona.id}`}
          className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm transition-colors hover:bg-secondary"
        >
          <MessageCircle className="h-4 w-4" />
          Спросить персону
        </Link>
      </div>

      <p className="mt-6 rounded-lg border border-border bg-secondary/30 p-4 text-sm leading-relaxed">
        {persona.narrative}
      </p>

      {/* 8 категорий DNA */}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Section title="1. Демография">
          <dl>
            <Field label="Пол" value={dna.demographics.gender} />
            <Field label="Возраст" value={`${dna.demographics.age} (${dna.demographics.ageGroup})`} />
            <Field label="Тип населённого пункта" value={dna.demographics.geo} />
            <Field label="Город" value={dna.demographics.city} />
            <Field label="Образование" value={dna.demographics.education} />
            <Field label="Род занятий" value={dna.demographics.occupation} />
            <Field label="Доход" value={dna.demographics.income} />
            <Field label="Дети" value={dna.demographics.children} />
            <Field label="Семейное положение" value={dna.demographics.maritalStatus} />
          </dl>
        </Section>

        <Section title="2. Big Five" hint="Шкала 1–5">
          <BigFiveChart value={dna.bigFive} />
        </Section>

        <Section title="3. Ценности и убеждения">
          <dl>
            <Field label="Базовые ценности" value={dna.values.coreValues} />
            <Field label="Социальные приоритеты" value={dna.values.socialPriorities} />
            <Field label="Культурный взгляд" value={dna.values.culturalOutlook} />
            <Field label="Философия" value={dna.values.philosophy} />
            <Field label="Отношение к будущему" value={dna.values.attitudeToFuture} />
          </dl>
        </Section>

        <Section
          title="4. Зрительское поведение"
          hint="Самая важная категория: именно она определяет реакцию на материал"
        >
          <dl>
            <Field label="Любимые жанры" value={dna.viewing.favouriteGenres} />
            <Field label="Избегаемые жанры" value={dna.viewing.avoidedGenres} />
            <Field label="Толерантность к насилию" value={dna.viewing.violenceTolerance} />
            <Field label="Толерантность к темпу" value={dna.viewing.paceTolerance} />
            <Field label="Толерантность к длине" value={dna.viewing.lengthTolerance} />
            <Field label="Лояльность к франшизам" value={dna.viewing.franchiseLoyalty} />
            <Field label="Лояльность к актёрам" value={dna.viewing.actorLoyalty} />
            <Field label="Влияние рекомендаций" value={dna.viewing.recommendationInfluence} />
            <Field label="Реакция на идеологический посыл" value={dna.viewing.reactionToIdeology} />
            <Field label="Реакция на рекламу" value={dna.viewing.reactionToAdvertising} />
            <Field label="Ожидания от продакшена" value={dna.viewing.productionExpectations} />
            <Field label="Attention span" value={dna.viewing.attentionSpan} />
          </dl>
        </Section>

        <Section title="5. Стиль общения" hint="Определяет, как звучат ответы персоны">
          <dl>
            <Field label="Тон" value={dna.communication.tone} />
            <Field label="Лексика" value={dna.communication.vocabulary} />
            <Field label="Многословность" value={dna.communication.verbosity} />
            <Field label="Юмор" value={dna.communication.humour} />
            <Field label="Манера критики" value={dna.communication.criticismStyle} />
          </dl>
        </Section>

        <Section title="6. Принятие решений">
          <dl>
            <Field label="Готовность к риску" value={dna.decisions.riskAppetite} />
            <Field label="Обдуманность" value={dna.decisions.deliberation} />
            <Field label="Влияние окружения" value={dna.decisions.peerInfluence} />
            <Field label="Доверие авторитету" value={dna.decisions.trustInAuthority} />
            <Field label="Чувствительность к цене" value={dna.decisions.priceSensitivity} />
          </dl>
        </Section>

        <Section title="7. Использование технологий">
          <dl>
            <Field label="Устройства" value={dna.technology.devices} />
            <Field label="Платформы" value={dna.technology.platforms} />
            <Field label="Контекст просмотра" value={dna.technology.viewingContext} />
            <Field label="Второй экран" value={dna.technology.secondScreen} />
          </dl>
        </Section>

        <Section title="8. Интересы и образ жизни">
          <dl>
            <Field label="Хобби" value={dna.lifestyle.hobbies} />
            <Field label="Ритм дня" value={dna.lifestyle.dailyRhythm} />
            <Field label="Социальная жизнь" value={dna.lifestyle.socialLife} />
            <Field label="Медиапотребление" value={dna.lifestyle.mediaDiet} />
            <Field label="Карьерный путь" value={dna.lifestyle.careerPath} />
          </dl>
        </Section>
      </div>

      {/* Ответы в контексте конкретного исследования */}
      {answer && (
        <section className="mt-6 rounded-lg border border-border bg-[hsl(222_47%_7%)] p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold">
              Ответы в исследовании «{MOCK_STUDY.contentTitle}»
            </h2>
            <Link
              href={`/runs/${MOCK_STUDY.id}`}
              className="text-xs text-muted-foreground underline-offset-4 hover:underline"
            >
              Открыть отчёт
            </Link>
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-5">
            {CRITERIA.map((c) => (
              <div key={c}>
                <p className="text-xs text-muted-foreground">{CRITERIA_LABELS[c]}</p>
                <p className="mt-0.5 text-xl font-semibold tabular-nums">{answer.scores[c]}</p>
              </div>
            ))}
          </div>

          <blockquote className="mt-4 border-l-2 border-border pl-4 text-sm leading-relaxed">
            «{answer.verbatim}»
          </blockquote>

          <div className="mt-4 flex flex-wrap gap-2">
            {answer.groundingRefs.map((r) => (
              <TimecodeRef key={r.timecode} timecode={r.timecode} note={r.note} />
            ))}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <span>Досмотрел(а) до {answer.watchedUntil}%</span>
            <span>Порекомендует: {answer.wouldRecommend ? "да" : "нет"}</span>
            <span>Эмоции: {answer.emotions.join(", ")}</span>
          </div>
        </section>
      )}
    </div>
  );
}
