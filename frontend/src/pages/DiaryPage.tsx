import { FormEvent, useEffect, useState } from "react";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { PageContainer } from "../components/common/PageContainer";
import { TripSelector } from "../components/common/TripSelector";
import { DiaryPhotoUploader } from "../components/diary/DiaryPhotoUploader";
import { useTripSelection } from "../hooks/useTripSelection";
import { diaryService, type DiaryInput } from "../services/diaryService";
import type { DiaryEntry, DiaryGenerated } from "../types";
import { formatDate, todayInputValue } from "../utils/format";

export function DiaryPage() {
  const { trips, selectedTripId, setSelectedTripId, isLoading: isTripLoading } = useTripSelection();
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [entryDate, setEntryDate] = useState(todayInputValue());
  const [photos, setPhotos] = useState<string[]>([]);
  const [emotionTags, setEmotionTags] = useState("설렘, 낭만");
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
      setError(err instanceof Error ? err.message : "다이어리를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  function buildInput(): DiaryInput {
    return {
      entry_date: entryDate,
      photo_urls: photos,
      emotion_tags: emotionTags.split(",").map((tag) => tag.trim()).filter(Boolean),
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
      setError(err instanceof Error ? err.message : "다이어리 생성에 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSave() {
    if (!selectedTripId) return;
    const entry = await diaryService.createEntry(selectedTripId, {
      ...buildInput(),
      ...(generated ?? {
        title: "파리 여행 기록",
        generated_diary_text: notes,
        mood_keywords: emotionTags.split(",").map((tag) => tag.trim()).filter(Boolean),
      }),
    });
    setEntries((current) => [entry, ...current]);
    setGenerated(null);
    setNotes("");
    setPhotos([]);
  }

  return (
    <PageContainer
      eyebrow="Diary"
      title="여행 다이어리"
      description="사진, 감정, 메모를 묶어 LLM 다이어리 생성 API로 보낼 수 있는 구조입니다."
      action={<TripSelector trips={trips} selectedTripId={selectedTripId} onChange={setSelectedTripId} />}
    >
      {isTripLoading || isLoading ? <LoadingState /> : null}
      {error ? <p className="form-error">{error}</p> : null}
      {!isTripLoading && !trips.length ? <EmptyState title="다이어리를 연결할 여행이 없습니다" description="먼저 여행 계획을 생성해 주세요." /> : null}
      {selectedTripId ? (
        <div className="two-column-layout diary-layout">
          <Card>
            <h2>오늘의 기억 입력</h2>
            <form className="stacked-form" onSubmit={handleGenerate}>
              <input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} />
              <input value={place} onChange={(event) => setPlace(event.target.value)} placeholder="장소 optional" />
              <input value={emotionTags} onChange={(event) => setEmotionTags(event.target.value)} placeholder="감정 태그, 쉼표로 구분" />
              <DiaryPhotoUploader photos={photos} onChange={setPhotos} />
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="오늘 기억하고 싶은 장면을 적어주세요." />
              <button type="submit" className="primary-button">감성 다이어리 생성</button>
            </form>
            {generated ? (
              <div className="generated-diary">
                <span className="eyebrow">Generated</span>
                <h3>{generated.title}</h3>
                <p>{generated.generated_diary_text}</p>
                <div className="tag-row">
                  {generated.mood_keywords.map((keyword) => (
                    <span key={keyword}>#{keyword}</span>
                  ))}
                </div>
                <button type="button" className="primary-button" onClick={handleSave}>저장하기</button>
              </div>
            ) : null}
          </Card>
          <section className="diary-list">
            {entries.length ? (
              entries.map((entry) => (
                <Card key={entry.id} className="diary-entry-card">
                  <span>{formatDate(entry.entry_date)} · {entry.place ?? "파리"}</span>
                  <h3>{entry.title ?? "여행 기록"}</h3>
                  <p>{entry.generated_diary_text ?? entry.notes}</p>
                  <div className="photo-preview-grid saved">
                    {entry.photo_urls.slice(0, 4).map((photo, index) => (
                      <img key={photo.slice(0, 40) + index} src={photo} alt={`저장된 사진 ${index + 1}`} />
                    ))}
                  </div>
                </Card>
              ))
            ) : (
              <EmptyState title="저장된 다이어리가 없습니다" description="사진과 감정을 입력해 첫 파리 여행 일기를 만들어보세요." />
            )}
          </section>
        </div>
      ) : null}
    </PageContainer>
  );
}
