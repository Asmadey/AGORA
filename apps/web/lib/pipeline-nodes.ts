import nodesJson from "../../../packages/shared/pipeline/nodes.json";

/**
 * Узлы конвейера для шкалы прогресса (задача #12).
 *
 * Список читается из packages/shared/pipeline/nodes.json — того же файла, из
 * которого его берёт граф воркера (`agent_core/pipeline/graph.py`). Держать
 * вторую копию в TypeScript нельзя: при правке конвейера копии расходятся, и
 * расхождение ничего не ломает заметно — шкала просто показывает не тот этап.
 * Найти такое тестом невозможно, потому что обе стороны по отдельности исправны.
 */

export interface PipelineNode {
  name: string;
  label: string;
  detail: string;
  /** Узел проходится только в длинном режиме — в короткой шкале его нет. */
  longOnly?: boolean;
}

export const PIPELINE_NODES: PipelineNode[] = (nodesJson as { nodes: PipelineNode[] }).nodes;

export function nodesForMode(mode: "short" | "long"): PipelineNode[] {
  return mode === "long" ? PIPELINE_NODES : PIPELINE_NODES.filter((n) => !n.longOnly);
}

export function nodeLabel(name: string): string {
  return PIPELINE_NODES.find((n) => n.name === name)?.label ?? name;
}
