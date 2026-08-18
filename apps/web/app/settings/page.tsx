"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, AlertCircle } from "lucide-react";
import { PageHeader } from "@/components/AppShell";
import {
  ModelPicker,
  ReasoningControls,
  useProviderModels,
} from "@/components/agora/ModelControls";
import { cn } from "@/lib/utils";
import {
  DEFAULT_SETTINGS,
  COST_CAP_BOUNDS,
  REPLICATION_VALUES,
  TEMPERATURE_BOUNDS,
  TEMPERATURE_STAGES,
  normalizeEndpoint,
  settingsEqual,
  type TenantSettings,
  type ReplicationCount,
} from "@/lib/settings";

/**
 * Настройки арендатора (задача #27, PRD §12).
 *
 * Три переключателя, каждый из которых напрямую влияет либо на стоимость прогона,
 * либо на его длительность. Поэтому рядом с каждым написано, чем именно платит
 * пользователь за выбор — иначе значения по умолчанию выбираются вслепую.
 *
 * Сохранение явное, а не автоматическое. Смена модели транскрипции меняет
 * поведение всех последующих прогонов команды; такое изменение должно быть
 * подтверждено нажатием, а не случайным кликом мимо. Пока изменения не сохранены,
 * это видно и уйти со страницы молча нельзя.
 */

type SaveState = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string };

export default function SettingsPage() {
  const [saved, setSaved] = useState<TenantSettings>(DEFAULT_SETTINGS);
  const [draft, setDraft] = useState<TenantSettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const provider = useProviderModels();
  // Ключ живёт отдельно от черновика настроек: он передаётся только на запись
  // и никогда не приходит с сервера, поэтому в `settingsEqual` ему места нет.
  const [apiKey, setApiKey] = useState("");

  // Введённый ключ тоже делает форму «грязной»: без этого кнопка сохранения
  // осталась бы неактивной, и ключ было бы некуда отправить.
  const dirty = !settingsEqual(saved, draft) || apiKey.trim().length > 0;

  /*
    Претензия к endpoint считается тем же кодом, что и на сервере, и живёт
    рядом с полем.

    Раньше она приходила ответом на сохранение и печаталась внизу экрана —
    общей строкой отказа. Владелец подвинул ползунок температуры и получил
    «endpoint: ожидается http(s)-адрес либо пусто»: поля он не трогал, находится
    оно в другой секции, и связать одно с другим было не с чем. Отказ был
    правильный, а сообщение — неадресным.
  */
  const endpointCheck = normalizeEndpoint(draft.endpoint);
  const endpointError = endpointCheck.ok ? null : endpointCheck.error;

  useEffect(() => {
    let cancelled = false;
    fetch("/api/settings")
      .then((r) => r.json())
      .then((data: { settings?: TenantSettings }) => {
        if (cancelled || !data.settings) return;
        setSaved(data.settings);
        setDraft(data.settings);
      })
      .catch(() => {
        /* остаёмся на значениях по умолчанию — они же показаны на экране */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Несохранённые правки легко потерять переходом по ссылке или закрытием вкладки.
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const patch = (p: Partial<TenantSettings>) => {
    setDraft((d) => ({ ...d, ...p }));
    setSave({ kind: "idle" });
  };

  const submit = async () => {
    setSave({ kind: "saving" });
    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        // Ключ отправляется отдельным полем и только при вводе: пустое
        // значение на сервере означает «не менять».
        body: JSON.stringify(apiKey.trim() ? { ...draft, apiKey: apiKey.trim() } : draft),
      });
      const data = await res.json();
      if (!res.ok) {
        setSave({
          kind: "error",
          message: Array.isArray(data.details) ? data.details.join("; ") : (data.error ?? "не удалось сохранить"),
        });
        return;
      }
      setSaved(data.settings);
      setDraft(data.settings);
      setSave({ kind: "saved" });
    } catch {
      setSave({ kind: "error", message: "сервер недоступен" });
    }
  };

  return (
    <>
      <PageHeader
        title="Настройки"
        subtitle="Применяются ко всем исследованиям команды. Значения можно переопределить при запуске конкретного прогона."
      />

      <div className="max-w-2xl space-y-4 p-8 pb-32">
        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Лимит вызовов модели</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Разбор кадров — самая дорогая стадия. Жёсткий лимит обрывает прогон при
            превышении: отчёт будет неполным, но счёт предсказуемым.
          </p>
          <div className="mt-4 flex gap-2">
            {(
              [
                { v: "auto", t: "Авто", d: "без потолка" },
                { v: "hard", t: "Жёсткий лимит", d: "оборвать при превышении" },
              ] as const
            ).map((o) => (
              <button
                key={o.v}
                onClick={() => patch({ costCap: o.v })}
                className={cn(
                  "flex-1 rounded-md border p-3 text-left transition-colors",
                  draft.costCap === o.v ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary",
                )}
              >
                <span className="block text-sm font-medium">{o.t}</span>
                <span className="mt-0.5 block text-xs text-slate">{o.d}</span>
              </button>
            ))}
          </div>
          {draft.costCap === "hard" && (
            <div className="mt-4 flex items-center gap-4">
              <input
                type="range"
                min={COST_CAP_BOUNDS.min}
                max={COST_CAP_BOUNDS.max}
                step={COST_CAP_BOUNDS.step}
                value={draft.costCapValue}
                onChange={(e) => patch({ costCapValue: Number(e.target.value) })}
                className="flex-1"
              />
              <span className="w-24 text-right text-sm tabular-nums">{draft.costCapValue} вызовов</span>
            </div>
          )}
        </section>

        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Модель транскрипции</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Транскрипция идёт на CPU. В образе воркера предзагружена одна модель —
            выбор второй увёл бы прогон качать полтора гигабайта весов уже после
            заливки ролика, и выглядело бы это случайным замедлением, а не
            нехваткой модели.
          </p>
          <div className="mt-4 flex gap-2">
            {(
              [
                { v: "large-v3", t: "whisper large-v3", d: "точнее, медленнее" },
              ] as const
            ).map((o) => (
              <button
                key={o.v}
                onClick={() => patch({ whisperModel: o.v })}
                className={cn(
                  "flex-1 rounded-md border p-3 text-left transition-colors",
                  draft.whisperModel === o.v ? "border-ink bg-secondary" : "border-hairline hover:bg-secondary",
                )}
              >
                <span className="block font-mono text-sm">{o.t}</span>
                <span className="mt-0.5 block text-xs text-slate">{o.d}</span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-slate">
            Выбор фиксируется в задаче на момент её создания и не меняется на лету:
            иначе прогон, начатый на одной модели, досчитался бы на другой, и отличить
            влияние модели от влияния материала стало бы невозможно.
          </p>
        </section>

        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Перекрытие по умолчанию</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Сколько раз каждая персона проходит анкету. Больше повторов — виден разброс
            и понятна устойчивость результата, но стоимость растёт пропорционально.
          </p>
          <div className="mt-4 flex gap-2">
            {REPLICATION_VALUES.map((n) => (
              <button
                key={n}
                onClick={() => patch({ defaultReplication: n as ReplicationCount })}
                className={cn(
                  "flex-1 rounded-md border py-2.5 text-sm transition-colors",
                  draft.defaultReplication === n
                    ? "border-ink bg-secondary"
                    : "border-hairline hover:bg-secondary",
                )}
              >
                ×{n}
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Температура</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Насколько модель отклоняется от самого вероятного продолжения. Ноль —
            всегда самый вероятный вариант, то есть повторяемость; выше — разброс
            формулировок. Одного значения на весь конвейер быть не может: персона
            обязана получиться непохожей на соседнюю, а проверяющий и аналитик —
            повторяемыми.
          </p>
          <div className="mt-4 space-y-4">
            {TEMPERATURE_STAGES.map((stage) => (
              <div key={stage.key}>
                <div className="flex items-baseline justify-between gap-4">
                  <label htmlFor={`t-${stage.key}`} className="text-sm">
                    {stage.label}
                  </label>
                  <span className="shrink-0 text-sm tabular-nums">
                    {draft.temperatures[stage.key].toFixed(1)}
                  </span>
                </div>
                <input
                  id={`t-${stage.key}`}
                  type="range"
                  min={TEMPERATURE_BOUNDS.min}
                  max={TEMPERATURE_BOUNDS.max}
                  step={TEMPERATURE_BOUNDS.step}
                  value={draft.temperatures[stage.key]}
                  onChange={(e) =>
                    patch({
                      temperatures: {
                        ...draft.temperatures,
                        [stage.key]: Number(e.target.value),
                      },
                    })
                  }
                  className="mt-2 w-full accent-foreground"
                />
                <p className="mt-1 text-xs leading-relaxed text-slate">
                  Рекомендуемое значение {stage.recommended}. {stage.hint}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-xs leading-relaxed text-slate">
            Значения фиксируются в задаче на момент запуска. Иначе персоны были бы
            созданы под одной температурой, а опрошены под другой, и разница в
            разбросе ответов выглядела бы свойством материала.
          </p>
        </section>

        <section className="rounded-lg border border-hairline bg-card p-6">
          <h2 className="text-sm font-semibold">Провайдер моделей</h2>
          <p className="mt-1 text-xs leading-relaxed text-slate">
            Список моделей приходит от провайдера живым запросом, а не зашит в код:
            зашитый устаревает молча — так у нас годами предлагались две модели
            транскрипции, а в образе лежала одна.
          </p>

          {provider?.error && (
            <p className="mt-3 rounded-md bg-warning-soft/60 px-3 py-2 text-xs text-warning">
              {provider.error}. Модель можно вписать в поле руками.
            </p>
          )}

          <div className="mt-4 space-y-5">
            <ModelPicker
              label="Модель рассуждения"
              hint="Отвечает за персон, аналитику и портреты сегментов."
              value={draft.models.text}
              onChange={(id) => patch({ models: { ...draft.models, text: id } })}
              info={provider}
              kind="text"
              fallback={provider?.current.text ?? ""}
            />

            <ModelPicker
              label="Модель зрения"
              hint="Разбирает кадры видео. Текстовая модель картинку не примет — один общий выбор сломал бы разбор кадров молча, уже после расшифровки."
              value={draft.models.vision}
              onChange={(id) => patch({ models: { ...draft.models, vision: id } })}
              info={provider}
              kind="vision"
              fallback={provider?.current.vision ?? ""}
            />

            {provider?.guessed && (
              <p className="text-xs text-slate">
                Провайдер не сообщает модальность модели — зрение опознано по имени.
                Если нужной модели нет в списке, впишите её имя в окружение сервера.
              </p>
            )}

            <div>
              <label htmlFor="provider-endpoint" className="block text-sm font-medium">
                Endpoint
              </label>
              <p className="mt-1 text-xs text-slate">
                Пусто — брать из окружения сервера
                {provider?.current.endpoint ? ` (${provider.current.endpoint})` : ""}.
              </p>
              <input
                id="provider-endpoint"
                name="provider-endpoint"
                type="url"
                inputMode="url"
                /*
                  Поле стоит вплотную к «Ключу провайдера» с type="password", и
                  менеджер паролей читает такую пару как форму входа: пароль —
                  туда, логин — в предыдущее текстовое поле. Заполнение приходит
                  событием change, то есть попадает в черновик молча, а всплывает
                  отказом сохранения совсем другой настройки.

                  autoComplete="off" браузеры для менеджеров паролей не соблюдают,
                  поэтому рядом стоят их собственные признаки. Имя полю дано по
                  той же причине: безымянное поле опознаётся эвристикой, а
                  названное — по имени.
                */
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                data-bwignore
                value={draft.endpoint}
                onChange={(e) => patch({ endpoint: e.target.value })}
                // Приведение к записываемому виду показывается сразу, а не
                // применяется втихую при сохранении: человек должен увидеть, что
                // именно уедет в базу.
                onBlur={() => {
                  const checked = normalizeEndpoint(draft.endpoint);
                  if (checked.ok && checked.value !== draft.endpoint) {
                    patch({ endpoint: checked.value });
                  }
                }}
                placeholder={provider?.current.endpoint || "https://…/v1"}
                aria-invalid={endpointError !== null}
                className={cn(
                  "mt-2 w-full rounded-md border bg-background px-3 py-2 font-mono text-sm",
                  endpointError ? "border-danger" : "border-hairline",
                )}
              />
              {endpointError && (
                <p className="mt-2 text-xs text-danger">
                  {endpointError}.{" "}
                  <button
                    type="button"
                    onClick={() => patch({ endpoint: DEFAULT_SETTINGS.endpoint })}
                    className="underline underline-offset-2"
                  >
                    Вернуть значение по умолчанию
                  </button>{" "}
                  — пустое поле означает «брать адрес из окружения сервера».
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium">Ключ провайдера</label>
              <p className="mt-1 text-xs text-slate">
                Действует: <span className="font-mono">{draft.apiKeyMask}</span>
              </p>
              <input
                type="password"
                name="provider-api-key"
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setSave({ kind: "idle" });
                }}
                placeholder="вставьте новый ключ, чтобы заменить"
                // "new-password", а не "off": первое браузеры соблюдают, второе
                // менеджеры паролей игнорируют — и заодно предлагают заполнить
                // соседнее поле логином.
                autoComplete="new-password"
                data-1p-ignore
                data-lpignore="true"
                data-bwignore
                className="mt-2 w-full rounded-md border border-hairline bg-background px-3 py-2 font-mono text-sm"
              />
              {/*
                Пустое поле означает «не менять», а не «стереть»: иначе
                сохранение соседней настройки убивало бы ключ, и заметили бы это
                на первом же прогоне, уже потратив расшифровку.

                Введённый ключ уходит на сервер один раз и обратно не
                возвращается никогда — даже владельцу: ответ уезжает в браузер,
                в его историю и в любой прокси по дороге.
              */}
              <p className="mt-2 text-xs leading-relaxed text-slate">
                Пустое поле — оставить прежний ключ. Введённый шифруется AES-256-GCM
                и хранится в базе только в зашифрованном виде; обратно он не
                отдаётся ни в одном ответе — показывается лишь маска. Ключ
                шифрования живёт в окружении обоих сервисов
                (<code className="font-mono">SETTINGS_SECRET</code>) и в резервную
                копию базы не попадает.
              </p>
            </div>
          </div>

          <div className="mt-6 border-t border-hairline pt-5">
            <h3 className="text-sm font-medium">Рассуждение</h3>
            <div className="mt-3">
              <ReasoningControls
                value={draft.reasoning}
                onChange={(reasoning) => patch({ reasoning })}
              />
            </div>
          </div>
        </section>
      </div>

      {/* Панель сохранения. Прижата к низу рабочей области, чтобы кнопка не уезжала
          за пределы экрана на длинной странице. */}
      <div className="sticky bottom-0 border-t border-hairline bg-background/95 px-8 py-4 backdrop-blur">
        <div className="flex max-w-2xl items-center gap-4">
          <button
            onClick={submit}
            // Претензия к endpoint держит кнопку: иначе отказ придёт с сервера
            // общей строкой внизу экрана, а поле, из-за которого он случился,
            // останется в другой секции без единой пометки.
            disabled={!dirty || endpointError !== null || save.kind === "saving" || loading}
            className="inline-flex items-center gap-2 rounded-md bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
          >
            {save.kind === "saving" && <Loader2 className="h-4 w-4 animate-spin" />}
            Сохранить
          </button>

          {dirty && (
            <button
              onClick={() => {
                setDraft(saved);
                setSave({ kind: "idle" });
              }}
              className="rounded-md border border-hairline px-4 py-2.5 text-sm transition-colors hover:bg-secondary"
            >
              Отменить
            </button>
          )}

          <span className="text-xs text-slate">
            {loading && "Загрузка…"}
            {!loading && dirty && endpointError && (
              <span className="text-danger">
                Endpoint провайдера задан неверно — исправьте его, чтобы сохранить
              </span>
            )}
            {!loading && dirty && !endpointError && "Есть несохранённые изменения"}
            {!loading && !dirty && save.kind === "saved" && (
              <span className="inline-flex items-center gap-1.5 text-success">
                <Check className="h-3.5 w-3.5" />
                Сохранено
              </span>
            )}
            {!loading && !dirty && save.kind !== "saved" && "Изменений нет"}
          </span>

          {save.kind === "error" && (
            <span className="inline-flex items-center gap-1.5 text-xs text-danger">
              <AlertCircle className="h-3.5 w-3.5" />
              {save.message}
            </span>
          )}
        </div>
      </div>
    </>
  );
}
