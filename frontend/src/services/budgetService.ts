import { apiRequest } from "./apiClient";
import type { BudgetItem, BudgetSummary } from "../types";

export const budgetService = {
  getBudget(tripId: string): Promise<BudgetSummary> {
    return apiRequest<BudgetSummary>(`/trips/${tripId}/budget`);
  },

  updateBudget(tripId: string, payload: Partial<BudgetSummary>): Promise<BudgetSummary> {
    return apiRequest<BudgetSummary>(`/trips/${tripId}/budget`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  addBudgetItem(tripId: string, payload: Omit<BudgetItem, "id">): Promise<BudgetSummary> {
    return apiRequest<BudgetSummary>(`/trips/${tripId}/budget/items`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  deleteBudgetItem(tripId: string, itemId: string): Promise<BudgetSummary> {
    return apiRequest<BudgetSummary>(`/trips/${tripId}/budget/items/${itemId}`, {
      method: "DELETE",
    });
  },
};
