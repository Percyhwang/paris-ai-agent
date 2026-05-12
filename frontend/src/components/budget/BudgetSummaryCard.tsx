import { useLanguage } from "../../store/LanguageContext";
import { formatCurrency } from "../../utils/format";
import type { BudgetSummary } from "../../types";

const BUDGET_SUMMARY_COPY = {
  ko: {
    expectedTotal: "예상 총액",
    totalDescription: "관광지 입장료, 숙박비, 추가 비용 기준",
    attractions: "관광지 입장료",
    hotels: "숙박비",
    custom: "추가 비용",
  },
  en: {
    expectedTotal: "Expected Total",
    totalDescription: "Based on attraction tickets, lodging, and extra costs",
    attractions: "Attraction Tickets",
    hotels: "Lodging",
    custom: "Extra Costs",
  },
} as const;

export function BudgetSummaryCard({ budget }: { budget: BudgetSummary }) {
  const { language } = useLanguage();
  const copy = BUDGET_SUMMARY_COPY[language];
  const customTotal = budget.custom_expenses.reduce((sum, item) => sum + item.amount, 0);

  return (
    <div className="budget-summary-grid">
      <div className="budget-total-card">
        <span>{copy.expectedTotal}</span>
        <strong>{formatCurrency(budget.grand_total, budget.currency, language)}</strong>
        <p>{copy.totalDescription}</p>
      </div>
      <div className="metric-card">
        <span>{copy.attractions}</span>
        <strong>{formatCurrency(budget.attraction_total, budget.currency, language)}</strong>
      </div>
      <div className="metric-card">
        <span>{copy.hotels}</span>
        <strong>{formatCurrency(budget.hotel_total, budget.currency, language)}</strong>
      </div>
      <div className="metric-card">
        <span>{copy.custom}</span>
        <strong>{formatCurrency(customTotal, budget.currency, language)}</strong>
      </div>
    </div>
  );
}
