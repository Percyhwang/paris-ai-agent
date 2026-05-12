import { FormEvent, useEffect, useState } from "react";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { TripSelector } from "../components/common/TripSelector";
import { DiaryPhotoUploader } from "../components/diary/DiaryPhotoUploader";
import { useTripSelection } from "../hooks/useTripSelection";
import { diaryService, type DiaryInput } from "../services/diaryService";
import { useLanguage } from "../store/LanguageContext";
import type { DiaryEntry, DiaryGenerated } from "../types";
import { formatDate, todayInputValue } from "../utils/format";

const DIARY_COPY = {
  ko: {
    eyebrow: "일기",
    title: "여행 다이어리",
    description: "사진, 감정, 메모를 묶어 LLM 다이어리 생성 API로 보낼 수 있는 구조입니다.",
    loading: "다이어리를 불러오는 중입니다",
    loadError: "다이어리를 불러오지 못했습니다.",
    generateError: "다이어리 생성에 실패했습니다.",
    noTripsTitle: "다이어리를 연결할 여행이 없습니다",
    noTripsDescription: "먼저 여행 계획을 생성해 주세요.",
    formTitle: "오늘의 기억 입력",
    placePlaceholder: "장소 (선택)",
    emotionPlaceholder: "감정 태그, 쉼표로 구분",
    notesPlaceholder: "오늘 기억하고 싶은 장면을 적어 주세요.",
    generate: "감성 다이어리 생성",
    generated: "생성됨",
    save: "저장하기",
    defaultGeneratedTitle: "파리 여행 기록",
    defaultPlace: "파리",
    defaultEntryTitle: "여행 기록",
    savedPhotoAlt: "저장된 사진",
    emptyTitle: "저장된 다이어리가 없습니다",
    emptyDescription: "사진과 감정을 입력해 첫 파리 여행 일기를 만들어 보세요.",
  },
  en: {
    eyebrow: "Diary",
    title: "Trip Diary",
    description: "Combine photos, emotions, and notes before sending them to the diary generation API.",
    loading: "Loading diary...",
    loadError: "Could not load diary entries.",
    generateError: "Could not generate the diary entry.",
    noTripsTitle: "No trip is available for diary entries",
    noTripsDescription: "Create a trip plan first.",
    formTitle: "Capture Today's Memory",
    placePlaceholder: "Place (optional)",
    emotionPlaceholder: "Emotion tags, separated by commas",
    notesPlaceholder: "Write a moment you want to remember from today.",
    generate: "Generate diary",
    generated: "Generated",
    save: "Save",
    defaultGeneratedTitle: "Paris Trip Note",
    defaultPlace: "Paris",
    defaultEntryTitle: "Trip Note",
    savedPhotoAlt: "Saved photo",
    emptyTitle: "No diary entries saved",
    emptyDescription: "Add photos and emotions to create your first Paris travel note.",
  },
} as const;

export function DiaryPage() {
  const { language } = useLanguage();
  const copy = DIARY_COPY[language];
  const { trips, selectedTripId, setSelectedTripId, isLoading: isTripLoading } = useTripSelection();
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [entryDate, setEntryDate] = useState(todayInputValue());
  const [photos, setPhotos] = useState<string[]>([]);
  const [emotionTags, setEmotionTags] = useState("");
  const [place, setPlace] = useState("");
  const [notes, setNotes] = useState("");
  const [generated, setGenerated] = useState<DiaryGenerated | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedTripId) return;
    loadEntries(selectedTripId);
  }, [selectedTripId]);

  async function loadEntries(tripId: string) {
    setIsLoading(true);
    setError(null);
    try {
      setEntries(await diaryService.listEntries(tripId));
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.loadError);
    } finally {
      setIsLoading(false);
    }
  }

  function buildInput(): DiaryInput {
    return {
      entry_date: entryDate,
      photo_urls: photos,
      emotion_tags: emotionTags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
      notes,
      place: place || undefined,
    };
  }

  async function handleGenerate(event: FormEvent) {
    event.preventDefault();
    if (!selectedTripId) return;
    setIsLoading(true);
    setError(null);
    try {
      setGenerated(await diaryService.generateDiary(selectedTripId, buildInput()));
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.generateError);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSave() {
    if (!selectedTripId) return;
    const entry = await diaryService.createEntry(selectedTripId, {
      ...buildInput(),
      ...(generated ?? {
        title: copy.defaultGeneratedTitle,
        generated_diary_text: notes,
        mood_keywords: emotionTags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      }),
    });
    setEntries((current) => [entry, ...current]);
    setGenerated(null);
    setNotes("");
    setPhotos([]);
  }

  return (
    <PageContainer
      eyebrow={copy.eyebrow}
      title={copy.title}
      description={copy.description}
      theme="diary"
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripLoading || isLoading ? <LoadingState label={copy.loading} /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripLoading && !trips.length ? <EmptyState title={copy.noTripsTitle} description={copy.noTripsDescription} /> : null}
      {selectedTripId ? (
        <div className="two-column-layout diary-layout">
          <Card>
            <h2>{copy.formTitle}</h2>
            <form className="stacked-form" onSubmit={handleGenerate}>
              <input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} />
              <input value={place} onChange={(event) => setPlace(event.target.value)} placeholder={copy.placePlaceholder} />
              <input value={emotionTags} onChange={(event) => setEmotionTags(event.target.value)} placeholder={copy.emotionPlaceholder} />
              <DiaryPhotoUploader photos={photos} onChange={setPhotos} />
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={copy.notesPlaceholder} />
              <button type="submit" className="primary-button">
                {copy.generate}
              </button>
            </form>
            {generated ? (
              <div className="generated-diary">
                <span className="eyebrow">{copy.generated}</span>
                <h3>{generated.title}</h3>
                <p>{generated.generated_diary_text}</p>
                <div className="tag-row">
                  {generated.mood_keywords.map((keyword) => (
                    <span key={keyword}>#{keyword}</span>
                  ))}
                </div>
                <button type="button" className="primary-button" onClick={handleSave}>
                  {copy.save}
                </button>
              </div>
            ) : null}
          </Card>
          <section className="diary-list">
            {entries.length ? (
              entries.map((entry) => (
                <Card key={entry.id} className="diary-entry-card">
                  <span>
                    {formatDate(entry.entry_date, language)} · {entry.place ?? copy.defaultPlace}
                  </span>
                  <h3>{entry.title ?? copy.defaultEntryTitle}</h3>
                  <p>{entry.generated_diary_text ?? entry.notes}</p>
                  <div className="photo-preview-grid saved">
                    {entry.photo_urls.slice(0, 4).map((photo, index) => (
                      <img key={photo.slice(0, 40) + index} src={photo} alt={`${copy.savedPhotoAlt} ${index + 1}`} />
                    ))}
                  </div>
                </Card>
              ))
            ) : (
              <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />
            )}
          </section>
        </div>
      ) : null}
    </PageContainer>
  );
}
