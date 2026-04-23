import { apiRequest } from "./apiClient";
import type { DiaryEntry, DiaryGenerated } from "../types";

export type DiaryInput = {
  entry_date: string;
  photo_urls: string[];
  emotion_tags: string[];
  notes: string;
  place?: string;
};

export const diaryService = {
  listEntries(tripId: string): Promise<DiaryEntry[]> {
    return apiRequest<DiaryEntry[]>(`/trips/${tripId}/diary`);
  },

  generateDiary(tripId: string, payload: DiaryInput): Promise<DiaryGenerated> {
    return apiRequest<DiaryGenerated>(`/trips/${tripId}/diary/generate`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  createEntry(tripId: string, payload: DiaryInput & Partial<DiaryGenerated>): Promise<DiaryEntry> {
    return apiRequest<DiaryEntry>(`/trips/${tripId}/diary`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};
