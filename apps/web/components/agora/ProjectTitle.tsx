"use client";

import { InlineRename } from "./InlineRename";

/**
 * Заголовок проекта с правкой на месте.
 *
 * Обёртка над общим `InlineRename`: у исследований теперь такая же правка, и
 * вторая копия того же кода разошлась бы с этой на первой же доработке — молча,
 * потому что оба экрана рядом никто не держит открытыми.
 */
export function ProjectTitle({
  id,
  name,
  action,
}: {
  id: string;
  name: string;
  /** Серверное действие переименования. То же, что было у прежней формы. */
  action: (formData: FormData) => void;
}) {
  return <InlineRename id={id} name={name} action={action} label="Название проекта" />;
}
