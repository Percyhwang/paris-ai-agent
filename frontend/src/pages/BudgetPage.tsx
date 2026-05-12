import { FormEvent, useEffect, useState } from "react";
import { BudgetSummaryCard } from "../components/budget/BudgetSummaryCard";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { TripSelector } from "../components/common/TripSelector";
import { useTripSelection } from "../hooks/useTripSelection";
import { budgetService } from "../services/budgetService";
import { useLanguage } from "../store/LanguageContext";
import type { BudgetItem, BudgetSummary } from "../types";
import { formatCurrency } from "../utils/format";

const BUDGET_COPY = {
  ko: {
    eyebrow: "예산",
    title: "여행 예산",
    description: "초기 범위의 관광지 입장료와 숙박비를 중심으로, 추가 비용을 직접 관리할 수 있습니다.",
    loading: "예산 정보를 불러오는 중입니다",
    loadError: "예산 정보를 불러오지 못했습니다.",
    noTripsTitle: "예산을 연결할 여행이 없습니다",
    noTripsDescription: "먼저 여행 계획을 생성해 주세요.",
    totalsTitle: "기본 예산 수정",
    attractions: "관광지 입장료",
    hotels: "숙박비",
    updateTotals: "총액 재계산",
    addItemTitle: "항목 추가",
    itemPlaceholder: "예: 몽마르트 브런치",
    addItem: "항목 추가",
    itemsTitle: "비용 항목",
    delete: "삭제",
    emptyTitle: "추가 비용이 없습니다",
    emptyDescription: "입장권, 호텔 보증금, 액티비티 비용 등을 추가할 수 있습니다.",
    categories: {
      custom: "기타 추가비용",
      attraction: "관광지",
      hotel: "숙박",
      other: "기타",
    },
  },
  en: {
    eyebrow: "Budget",
    title: "Trip Budget",
    description: "Manage attraction tickets, lodging, and any additional travel costs in one place.",
    loading: "Loading budget...",
    loadError: "Could not load budget details.",
    noTripsTitle: "No trip is available for budgeting",
    noTripsDescription: "Create a trip plan first.",
    totalsTitle: "Edit Base Budget",
    attractions: "Attraction tickets",
    hotels: "Lodging",
    updateTotals: "Recalculate total",
    addItemTitle: "Add Item",
    itemPlaceholder: "E.g. Montmartre brunch",
    addItem: "Add item",
    itemsTitle: "Expense Items",
    delete: "Delete",
    emptyTitle: "No extra costs yet",
    emptyDescription: "Add tickets, deposits, activities, or other travel expenses.",
    categories: {
      custom: "Custom expense",
      attraction: "Attraction",
      hotel: "Hotel",
      other: "Other",
    },
  },
} as const;

export function BudgetPage() {
  const { language } = useLanguage();
  const copy = BUDGET_COPY[language];
  const { trips, selectedTripId, setSelectedTripId, isLoading: isTripLoading } = useTripSelection();
  const [budget, setBudget] = useState<BudgetSummary | null>(null);
  const [attractionTotal, setAttractionTotal] = useState(0);
  const [hotelTotal, setHotelTotal] = useState(0);
  const [itemTitle, setItemTitle] = useState("");
  const [itemAmount, setItemAmount] = useState(0);
  const [itemCategory, setItemCategory] = useState<BudgetItem["category"]>("custom");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedTripId) return;
    loadBudget(selectedTripId);
  }, [selectedTripId]);

  async function loadBudget(tripId: string) {
    setIsLoading(true);
    setError(null);
    try {
      const data = await budgetService.getBudget(tripId);
      setBudget(data);
      setAttractionTotal(data.attraction_total);
      setHotelTotal(data.hotel_total);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.loadError);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleTotalsSubmit(event: FormEvent) {
    event.preventDefault();
    if (!selectedTripId || !budget) return;
    const updated = await budgetService.updateBudget(selectedTripId, {
      attraction_total: attractionTotal,
      hotel_total: hotelTotal,
      currency: budget.currency,
    });
    setBudget(updated);
  }

  async function handleAddItem(event: FormEvent) {
    event.preventDefault();
    if (!selectedTripId || !budget || !itemTitle.trim()) return;
    const updated = await budgetService.addBudgetItem(selectedTripId, {
      title: itemTitle.trim(),
      amount: itemAmount,
      category: itemCategory,
      currency: budget.currency,
      day_number: null,
      note: null,
    });
    setBudget(updated);
    setItemTitle("");
    setItemAmount(0);
    setItemCategory("custom");
  }

  async function handleDeleteItem(itemId: string) {
    if (!selectedTripId) return;
    setBudget(await budgetService.deleteBudgetItem(selectedTripId, itemId));
  }

  return (
    <PageContainer
      eyebrow={copy.eyebrow}
      title={copy.title}
      description={copy.description}
      theme="budget"
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripLoading || isLoading ? <LoadingState label={copy.loading} /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripLoading && !trips.length ? <EmptyState title={copy.noTripsTitle} description={copy.noTripsDescription} /> : null}
      {budget ? (
        <>
          <BudgetSummaryCard budget={budget} />
          <div className="two-column-layout">
            <Card>
              <h2>{copy.totalsTitle}</h2>
              <form className="stacked-form" onSubmit={handleTotalsSubmit}>
                <label>
                  {copy.attractions}
                  <input type="number" min="0" value={attractionTotal} onChange={(event) => setAttractionTotal(Number(event.target.value))} />
                </label>
                <label>
                  {copy.hotels}
                  <input type="number" min="0" value={hotelTotal} onChange={(event) => setHotelTotal(Number(event.target.value))} />
                </label>
                <button type="submit" className="primary-button">
                  {copy.updateTotals}
                </button>
              </form>
            </Card>
            <Card>
              <h2>{copy.addItemTitle}</h2>
              <form className="stacked-form" onSubmit={handleAddItem}>
                <select value={itemCategory} onChange={(event) => setItemCategory(event.target.value as BudgetItem["category"])}>
                  <option value="custom">{copy.categories.custom}</option>
                  <option value="attraction">{copy.categories.attraction}</option>
                  <option value="hotel">{copy.categories.hotel}</option>
                  <option value="other">{copy.categories.other}</option>
                </select>
                <input value={itemTitle} onChange={(event) => setItemTitle(event.target.value)} placeholder={copy.itemPlaceholder} required />
                <input type="number" min="0" value={itemAmount} onChange={(event) => setItemAmount(Number(event.target.value))} />
                <button type="submit" className="primary-button">
                  {copy.addItem}
                </button>
              </form>
            </Card>
          </div>
          <section className="budget-items">
            <h2>{copy.itemsTitle}</h2>
            {budget.custom_expenses.length ? (
              budget.custom_expenses.map((item) => (
                <Card key={item.id} className="budget-item-card">
                  <div>
                    <span className="category-pill">{copy.categories[item.category]}</span>
                    <h3>{item.title}</h3>
                  </div>
                  <strong>{formatCurrency(item.amount, item.currency, language)}</strong>
                  <button type="button" className="ghost-button small" onClick={() => handleDeleteItem(item.id)}>
                    {copy.delete}
                  </button>
                </Card>
              ))
            ) : (
              <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />
            )}
          </section>
        </>
      ) : null}
    </PageContainer>
  );
}
