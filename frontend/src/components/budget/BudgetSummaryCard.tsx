import { formatCurrency } from "../../utils/format";
import type { BudgetSummary } from "../../types";

export function BudgetSummaryCard({ budget }: { budget: BudgetSummary }) {
  const customTotal = budget.custom_expenses.reduce((sum, item) => sum + item.amount, 0);

  return (
    <div className="budget-summary-grid">
      <div className="budget-total-card">
        <span>예상 총액</span>
        <strong>{formatCurrency(budget.grand_total, budget.currency)}</strong>
        <p>관광지 입장료, 숙박비, 추가 비용 기준</p>
      </div>
      <div className="metric-card">
        <span>관광지 입장료</span>
        <strong>{formatCurrency(budget.attraction_total, budget.currency)}</strong>
      </div>
      <div className="metric-card">
        <span>숙박비</span>
        <strong>{formatCurrency(budget.hotel_total, budget.currency)}</strong>
      </div>
      <div className="metric-card">
        <span>추가 비용</span>
        <strong>{formatCurrency(customTotal, budget.currency)}</strong>
      </div>
    </div>
  );
}
