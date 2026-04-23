import { apiRequest } from "./apiClient";
import type { Place } from "../types";

export const placeService = {
  listPlaces(params: { search?: string; category?: string; sort?: string } = {}): Promise<Place[]> {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.category && params.category !== "all") query.set("category", params.category);
    if (params.sort) query.set("sort", params.sort);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiRequest<Place[]>(`/places${suffix}`, { auth: false });
  },

  getPlace(placeId: string): Promise<Place> {
    return apiRequest<Place>(`/places/${placeId}`, { auth: false });
  },
};
