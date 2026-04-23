import { FormEvent, useEffect, useState } from "react";
import { BudgetSummaryCard } from "../components/budget/BudgetSummaryCard";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { TripSelector } from "../components/common/TripSelector";
import { useTripSelection } from "../hooks/useTripSelection";
import { budgetService } from "../services/budgetService";
import type { BudgetItem, BudgetSummary } from "../types";
import { formatCurrency } from "../utils/format";

export function BudgetPage() {
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
      setError(err instanceof Error ? err.message : "예산 정보를 불러오지 못했습니다.");
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
      eyebrow="Budget"
      title="여행 예산"
      description="초기 범위는 관광지 입장료와 숙박비 중심이며, 추가 비용을 직접 관리할 수 있습니다."
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripLoading || isLoading ? <LoadingState /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripLoading && !trips.length ? <EmptyState title="예산을 연결할 여행이 없습니다" description="먼저 여행 계획을 생성해 주세요." /> : null}
      {budget ? (
        <>
          <BudgetSummaryCard budget={budget} />
          <div className="two-column-layout">
            <Card>
              <h2>기본 예산 수정</h2>
              <form className="stacked-form" onSubmit={handleTotalsSubmit}>
                <label>
                  관광지 입장료
                  <input type="number" min="0" value={attractionTotal} onChange={(event) => setAttractionTotal(Number(event.target.value))} />
                </label>
                <label>
                  숙박비
                  <input type="number" min="0" value={hotelTotal} onChange={(event) => setHotelTotal(Number(event.target.value))} />
                </label>
                <button type="submit" className="primary-button">총액 재계산</button>
              </form>
            </Card>
            <Card>
              <h2>항목 추가</h2>
              <form className="stacked-form" onSubmit={handleAddItem}>
                <select value={itemCategory} onChange={(event) => setItemCategory(event.target.value as BudgetItem["category"])}>
                  <option value="custom">기타 추가비용</option>
                  <option value="attraction">관광지</option>
                  <option value="hotel">숙박</option>
                  <option value="other">기타</option>
                </select>
                <input value={itemTitle} onChange={(event) => setItemTitle(event.target.value)} placeholder="예: 세느강 크루즈" required />
                <input type="number" min="0" value={itemAmount} onChange={(event) => setItemAmount(Number(event.target.value))} />
                <button type="submit" className="primary-button">항목 추가</button>
              </form>
            </Card>
          </div>
          <section className="budget-items">
            <h2>비용 항목</h2>
            {budget.custom_expenses.length ? (
              budget.custom_expenses.map((item) => (
                <Card key={item.id} className="budget-item-card">
                  <div>
                    <span className="category-pill">{item.category}</span>
                    <h3>{item.title}</h3>
                  </div>
                  <strong>{formatCurrency(item.amount, item.currency)}</strong>
                  <button type="button" className="ghost-button small" onClick={() => handleDeleteItem(item.id)}>삭제</button>
                </Card>
              ))
            ) : (
              <EmptyState title="추가 비용이 없습니다" description="입장권, 호텔 보증금, 특별 액티비티 비용을 추가할 수 있습니다." />
            )}
          </section>
        </>
      ) : null}
    </PageContainer>
  );
}
