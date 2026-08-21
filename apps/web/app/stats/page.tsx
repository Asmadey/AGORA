import { PageHeader } from "@/components/AppShell";
import { ConsumptionTable } from "@/components/agora/ConsumptionTable";

/**
 * Статистика потребления и расходов.
 *
 * Данные берутся у API контроля затрат cloud.ru — то есть у того же источника,
 * по которому выставляется счёт. Считать расход по своим логам вызовов было бы
 * дешевле, но это была бы вторая арифметика: она расходится со счётом на
 * округлениях тарифа и на всём, что провайдер тарифицирует иначе, чем мы
 * считаем, — и объяснять расхождение пришлось бы каждый месяц.
 */
export const dynamic = "force-dynamic";

export default function StatsPage() {
  return (
    <>
      <PageHeader
        title="Статистика"
        subtitle="Потребление токенов и расходы по данным биллинга cloud.ru"
      />
      <div className="p-8">
        <ConsumptionTable />
      </div>
    </>
  );
}
