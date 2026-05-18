import type { Language } from "../i18n/config";

export type TimePeriodKey = "dawn" | "morning" | "lunch" | "afternoon" | "evening" | "night";

export const TIME_PERIOD_LABELS: Record<Language, Record<TimePeriodKey, string>> = {
  ko: {
    dawn: "새벽",
    morning: "아침",
    lunch: "점심",
    afternoon: "오후",
    evening: "저녁",
    night: "밤",
  },
  en: {
    dawn: "Dawn",
    morning: "Morning",
    lunch: "Lunch",
    afternoon: "Afternoon",
    evening: "Evening",
    night: "Night",
  },
};

export const TIME_PERIOD_BOUNDARY_CASES: Array<{ time: string; expected: TimePeriodKey }> = [
  { time: "00:00", expected: "dawn" },
  { time: "05:59", expected: "dawn" },
  { time: "06:00", expected: "morning" },
  { time: "09:15", expected: "morning" },
  { time: "10:59", expected: "morning" },
  { time: "11:00", expected: "lunch" },
  { time: "12:00", expected: "lunch" },
  { time: "13:56", expected: "lunch" },
  { time: "13:59", expected: "lunch" },
  { time: "14:00", expected: "afternoon" },
  { time: "14:10", expected: "afternoon" },
  { time: "17:59", expected: "afternoon" },
  { time: "18:00", expected: "evening" },
  { time: "19:30", expected: "evening" },
  { time: "21:59", expected: "evening" },
  { time: "22:00", expected: "night" },
  { time: "23:59", expected: "night" },
];

export function parseClockToMinutes(clock?: string | null) {
  if (!clock) return null;

  const match = /^(\d{1,2}):(\d{2})$/.exec(clock.trim());
  if (!match) return null;

  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours < 0 || minutes < 0 || minutes > 59) return null;
  if (hours > 23) return 23 * 60 + 59;

  return hours * 60 + minutes;
}

export function getTimePeriodKeyFromMinutes(minutes: number): TimePeriodKey {
  if (minutes < 6 * 60) return "dawn";
  if (minutes < 11 * 60) return "morning";
  if (minutes < 14 * 60) return "lunch";
  if (minutes < 18 * 60) return "afternoon";
  if (minutes < 22 * 60) return "evening";
  return "night";
}

export function getTimePeriodKey(clock?: string | null): TimePeriodKey {
  const minutes = parseClockToMinutes(clock);
  return minutes === null ? "morning" : getTimePeriodKeyFromMinutes(minutes);
}

export function getTimePeriodLabel(clock: string | null | undefined, language: Language) {
  return TIME_PERIOD_LABELS[language][getTimePeriodKey(clock)];
}

export function getTimePeriodBoundaryFailures() {
  return TIME_PERIOD_BOUNDARY_CASES.filter(({ time, expected }) => getTimePeriodKey(time) !== expected);
}
