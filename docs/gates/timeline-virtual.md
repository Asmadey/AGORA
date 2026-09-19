# Ворота таймлайна

Эти ворота проверяют именно эффект виртуализации. `content-visibility` и
`loading="lazy"` сами по себе не уменьшают число `Cell` в дереве, поэтому
проверяется число тяжёлых узлов, а не только наличие CSS-атрибута.

## Окно и границы

CHECK: `cd apps/web && node --conditions=react-server --test lib/timeline-render-window.test.ts`

EXPECT: все тесты окна зелёные; проверены запас сверху и снизу, начало и конец списка, ноль, одна ячейка, окно больше списка и активная ячейка вне видимой области.

## Замер 322 ячеек

CHECK: `cd apps/web && node --conditions=react-server --test lib/timeline-render-window.test.ts | grep 'timeline Cell nodes:'`

EXPECT: `timeline Cell nodes: before=322 after=9`

До правки в списке присутствовали 322 тяжёлые `Cell` с превью и текстом. После
правки для трёх видимых ячеек и запаса в три строки сверху и снизу монтируются
9 тяжёлых `Cell`; к концу списка окно прижимается к границе и не создаёт
фиктивных индексов.

## Печать и поиск

CHECK: `cd apps/web && node --conditions=react-server --test lib/timeline-render-window.test.ts --test-name-pattern='печать раскрывает все ячейки'`

EXPECT: тест печати зелёный; `beforeprint` включает полный рендер, а поисковый индекс содержит все реплики вне виртуального окна.
