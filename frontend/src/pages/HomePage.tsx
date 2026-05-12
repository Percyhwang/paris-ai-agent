import { FormEvent, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link, useNavigate } from "react-router-dom";
import { tripService } from "../services/tripService";
import { useAuth } from "../store/AuthContext";
import { useLanguage } from "../store/LanguageContext";

const DEFAULT_HERO_IMAGE = "/images/paris-sunset-hero.png";

const HOME_COPY = {
  ko: {
    vibeTags: ["낭만적인 파리", "미식 중심 파리", "여유로운 산책 파리"],
    guideMessages: [
      {
        id: "mood",
        label: "감성",
        title: "어떤 분위기의 파리를 원하시나요?",
        description: "감성 카페, 미술관, 야경 코스처럼 분위기에 맞는 루트를 같이 골라드릴게요.",
      },
      {
        id: "pace",
        label: "동선",
        title: "천천히 걸어도 충분해요 :)",
        description: "빽빽한 일정보다 여유 있게 걷고 싶다면, 속도에 맞춘 코스로 다듬어드릴게요.",
      },
      {
        id: "budget",
        label: "예산",
        title: "취향과 예산을 함께 맞춰드릴게요.",
        description: "가볍게 즐기는 일정부터 특별한 하루까지 분위기에 맞게 정리해드려요.",
      },
    ],
    promptExamples: [
      {
        label: "미술관 + 야경",
        guideId: "mood",
        prompt: "루브르랑 오르세를 여유롭게 보고, 마지막 밤에는 야경까지 있는 파리 3박 4일 일정 추천해줘",
      },
      {
        label: "카페 + 산책",
        guideId: "pace",
        prompt: "감성 카페와 예쁜 골목 산책이 많은 여유로운 파리 2박 3일 코스 추천해줘",
      },
      {
        label: "미식 중심",
        guideId: "budget",
        prompt: "브런치부터 디너까지 분위기 좋은 곳을 묶어준 파리 미식 일정 추천해줘",
      },
    ],
    landmarkPrompts: [
      {
        id: "eiffel",
        name: "에펠탑",
        subtitle: "반짝이는 야경 코스",
        guideId: "mood",
        prompt: "에펠탑 야경과 센강 산책이 들어간 낭만적인 파리 일정 추천해줘",
      },
      {
        id: "notre-dame",
        name: "노트르담",
        subtitle: "고즈넉한 산책 코스",
        guideId: "pace",
        prompt: "노트르담 주변 산책과 예쁜 골목이 어울리는 여유로운 파리 일정 추천해줘",
      },
    ],
    heroStatus: "Paris mood planner",
    kicker: "원하는 분위기를 들려주세요",
    titleTop: "파리, 취향대로",
    titleBottom: "골라볼까요?",
    heroDescription: "가고 싶은 분위기만 말해주시면 돼요. 취향에 맞는 일정과 예산을 바로 추천해드릴게요.",
    tripRequest: "Trip request",
    requestTitle: "가고 싶은 분위기만 말해주시면 돼요.",
    requestDescription: "한 문장, 몇 개의 키워드, 짧은 메모만으로도 괜찮아요.",
    requestHint: "1문장부터 시작",
    assistantTitle: "짧게 적어도 괜찮아요 :)",
    assistantDescription: "미술관, 야경, 카페처럼 떠오르는 단어만 적어도 충분해요.",
    memoLabel: "나의 여행 메모",
    memoPlaceholder: "예쁜 산책길과 미술관, 마지막 밤의 야경이 있는 파리 3박 4일 일정 추천해줘",
    submitError: "여행 플랜을 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.",
    supportLoggedIn: "입력한 문장으로 바로 일정 초안을 만들어드릴게요.",
    supportLoggedOutPrefix: "로그인하면 일정, 예산, 예약, 기록까지 이어서 관리할 수 있어요. ",
    supportLoggedOutLink: "Google로 로그인",
    generating: "여행 만들는 중...",
    generate: "내 여행 만들기",
    guideEyebrow: "Paris guide",
    guideTitle: "다정한 파리 가이드가 같이 계획해드릴게요.",
    bubbleEyebrow: "Paris friends",
    bubbleTitle: "어떤 계획이 끌릴까요?",
    stickerLabel: "Paris landmark stickers",
    tabAria: "guide messages",
    exampleTitle: "예시로 바로 써보기",
    exampleDescription: "누르면 입력창에 바로 들어가요.",
    uploadBackground: "배경 바꾸기",
    resetBackground: "기본 배경",
  },
  en: {
    vibeTags: ["Romantic Paris", "Food-focused Paris", "Slow-stroll Paris"],
    guideMessages: [
      {
        id: "mood",
        label: "Mood",
        title: "What kind of Paris are you in the mood for?",
        description: "We can shape the route around cafe scenes, museums, river walks, or a night-view itinerary.",
      },
      {
        id: "pace",
        label: "Pace",
        title: "A slower pace is completely enough :)",
        description: "If you want room to wander instead of rushing, we can build a softer route around that rhythm.",
      },
      {
        id: "budget",
        label: "Budget",
        title: "We can match your taste and budget together.",
        description: "From light everyday plans to a more special Paris day, the route can stay aligned with your range.",
      },
    ],
    promptExamples: [
      {
        label: "Museums + night view",
        guideId: "mood",
        prompt: "Build a 3-night Paris itinerary with the Louvre, Musee d'Orsay, and a beautiful night view on the final evening.",
      },
      {
        label: "Cafes + walks",
        guideId: "pace",
        prompt: "Recommend a relaxed 2-night Paris route with charming cafes and quiet streets for walking.",
      },
      {
        label: "Food-focused trip",
        guideId: "budget",
        prompt: "Plan a Paris food itinerary with a nice flow from brunch to dinner in atmospheric neighborhoods.",
      },
    ],
    landmarkPrompts: [
      {
        id: "eiffel",
        name: "Eiffel Tower",
        subtitle: "Sparkling night route",
        guideId: "mood",
        prompt: "Recommend a romantic Paris route with the Eiffel Tower at night and a Seine walk.",
      },
      {
        id: "notre-dame",
        name: "Notre-Dame",
        subtitle: "Quiet walking route",
        guideId: "pace",
        prompt: "Recommend a relaxed Paris route with a walk around Notre-Dame and beautiful side streets.",
      },
    ],
    heroStatus: "Paris mood planner",
    kicker: "Tell us the feeling you want",
    titleTop: "Paris,",
    titleBottom: "your way.",
    heroDescription: "Just describe the mood you want. We will turn it into a route, budget feel, and travel direction right away.",
    tripRequest: "Trip request",
    requestTitle: "A few words about your ideal Paris is enough.",
    requestDescription: "A sentence, a few keywords, or a rough note all work well.",
    requestHint: "Start with one line",
    assistantTitle: "Short notes are totally fine :)",
    assistantDescription: "Museums, night views, cafes, or just a feeling are enough to get started.",
    memoLabel: "My travel note",
    memoPlaceholder: "Create a 3-night Paris plan with scenic walks, museums, and a beautiful final-night view.",
    submitError: "Something went wrong while building your trip plan. Please try again shortly.",
    supportLoggedIn: "We can turn your note into a first draft itinerary right away.",
    supportLoggedOutPrefix: "Sign in to keep your trip plan, budget, reservations, and diary connected. ",
    supportLoggedOutLink: "Sign in with Google",
    generating: "Building your trip...",
    generate: "Create My Trip",
    guideEyebrow: "Paris guide",
    guideTitle: "A friendly Paris guide can shape the plan with you.",
    bubbleEyebrow: "Paris friends",
    bubbleTitle: "Which route feels right?",
    stickerLabel: "Paris landmark stickers",
    tabAria: "guide messages",
    exampleTitle: "Try a ready-made example",
    exampleDescription: "Tap once and it drops straight into the input box.",
    uploadBackground: "Change Background",
    resetBackground: "Reset Background",
  },
} as const;

export function HomePage() {
  const navigate = useNavigate();
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const { isAuthenticated } = useAuth();
  const { language } = useLanguage();
  const copy = HOME_COPY[language];
  const [prompt, setPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeGuideId, setActiveGuideId] = useState("mood");
  const [heroImage, setHeroImage] = useState(localStorage.getItem("parisHeroPhoto") || DEFAULT_HERO_IMAGE);

  const activeGuide = useMemo(
    () => copy.guideMessages.find((item) => item.id === activeGuideId) ?? copy.guideMessages[0],
    [activeGuideId, copy.guideMessages],
  );
  const heroStyle = heroImage ? ({ "--hero-image": `url(${heroImage})` } as CSSProperties) : undefined;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim()) return;
    if (!isAuthenticated) {
      navigate("/login", { state: { from: { pathname: "/" } } });
      return;
    }

    setIsGenerating(true);
    setError(null);
    try {
      const trip = await tripService.generateTrip({ prompt: prompt.trim() });
      navigate(`/trips/${trip.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.submitError);
    } finally {
      setIsGenerating(false);
    }
  }

  function applyPrompt(nextPrompt: string, nextGuideId?: string) {
    setPrompt(nextPrompt);
    if (nextGuideId) {
      setActiveGuideId(nextGuideId);
    }

    requestAnimationFrame(() => {
      promptRef.current?.focus();
    });
  }

  function handleBackgroundUpload(file: File | undefined) {
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        localStorage.setItem("parisHeroPhoto", reader.result);
        setHeroImage(reader.result);
      }
    };
    reader.readAsDataURL(file);
  }

  function handleResetBackground() {
    localStorage.removeItem("parisHeroPhoto");
    setHeroImage(DEFAULT_HERO_IMAGE);
  }

  return (
    <main className="home-page" style={heroStyle}>
      <div className="hero-overlay" />
      <section className="hero-content">
        <div className="hero-grid">
          <div className="hero-main-column">
            <div className="hero-intro">
              <div className="hero-badge-row">
                <span className="eyebrow light">Paris AI Agent</span>
                <span className="hero-status-pill">{copy.heroStatus}</span>
              </div>
              <div className="hero-headline-stack">
                <p className="hero-kicker">{copy.kicker}</p>
                <h1>
                  <span>{copy.titleTop}</span>
                  <span>{copy.titleBottom}</span>
                </h1>
                <p className="hero-description">{copy.heroDescription}</p>
              </div>
              <div className="hero-mini-chips" aria-label="travel styles">
                {copy.vibeTags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </div>

            <form className="conversation-panel" onSubmit={handleSubmit}>
              <div className="conversation-head">
                <div className="conversation-copy">
                  <span className="prompt-panel-eyebrow">{copy.tripRequest}</span>
                  <h2>{copy.requestTitle}</h2>
                  <p>{copy.requestDescription}</p>
                </div>
                <span className="conversation-hint">{copy.requestHint}</span>
              </div>

              <div className="conversation-thread">
                <div className="assistant-inline-message">
                  <span className="assistant-inline-avatar">PA</span>
                  <div className="assistant-inline-bubble">
                    <strong>{copy.assistantTitle}</strong>
                    <p>{copy.assistantDescription}</p>
                  </div>
                </div>

                <label className="composer-row" htmlFor="trip-request">
                  <span className="composer-avatar">ME</span>
                  <div className="composer-shell">
                    <span className="composer-label">{copy.memoLabel}</span>
                    <textarea
                      ref={promptRef}
                      id="trip-request"
                      className="conversation-textarea"
                      value={prompt}
                      onChange={(event) => setPrompt(event.target.value)}
                      placeholder={copy.memoPlaceholder}
                    />
                  </div>
                </label>
              </div>

              {error ? <p className="form-error hero-form-error">{error}</p> : null}

              <div className="conversation-foot">
                <p className="prompt-support-note">
                  {isAuthenticated ? (
                    copy.supportLoggedIn
                  ) : (
                    <>
                      {copy.supportLoggedOutPrefix}
                      <Link to="/login">{copy.supportLoggedOutLink}</Link>
                    </>
                  )}
                </p>
                <button type="submit" className="primary-button prompt-submit-button" disabled={isGenerating}>
                  {isGenerating ? copy.generating : copy.generate}
                </button>
              </div>
            </form>
          </div>

          <aside className="hero-side-panel">
            <div className="mascot-card">
              <div className="mascot-header">
                <span className="eyebrow">{copy.guideEyebrow}</span>
                <h3>{copy.guideTitle}</h3>
              </div>

              <div className="mascot-scene">
                <div className="assistant-bubble-card">
                  <span className="assistant-bubble-eyebrow">{copy.bubbleEyebrow}</span>
                  <strong>{copy.bubbleTitle}</strong>
                  <p>{activeGuide.description}</p>
                </div>

                <div className="paris-sticker-row" aria-label={copy.stickerLabel}>
                  <button
                    type="button"
                    className="paris-sticker eiffel-sticker"
                    onClick={() => applyPrompt(copy.landmarkPrompts[0].prompt, copy.landmarkPrompts[0].guideId)}
                  >
                    <div className="sticker-emoji sticker-eiffel" aria-hidden="true">
                      <span className="sticker-eiffel-light" />
                      <span className="sticker-eiffel-top" />
                      <span className="sticker-eiffel-body" />
                      <span className="sticker-eiffel-arch" />
                      <span className="sticker-eiffel-leg sticker-eiffel-leg-left" />
                      <span className="sticker-eiffel-leg sticker-eiffel-leg-right" />
                      <span className="sticker-eiffel-arm sticker-eiffel-arm-left" />
                      <span className="sticker-eiffel-arm sticker-eiffel-arm-right" />
                      <span className="sticker-face-eye sticker-face-eye-left" />
                      <span className="sticker-face-eye sticker-face-eye-right" />
                      <span className="sticker-face-mouth" />
                      <span className="sticker-face-cheek sticker-face-cheek-left" />
                      <span className="sticker-face-cheek sticker-face-cheek-right" />
                    </div>
                    <strong>{copy.landmarkPrompts[0].name}</strong>
                    <p>{copy.landmarkPrompts[0].subtitle}</p>
                  </button>

                  <button
                    type="button"
                    className="paris-sticker notre-dame-sticker"
                    onClick={() => applyPrompt(copy.landmarkPrompts[1].prompt, copy.landmarkPrompts[1].guideId)}
                  >
                    <div className="sticker-emoji sticker-notre-dame" aria-hidden="true">
                      <span className="sticker-notre-roof" />
                      <span className="sticker-notre-tower sticker-notre-tower-left" />
                      <span className="sticker-notre-tower sticker-notre-tower-right" />
                      <span className="sticker-notre-body" />
                      <span className="sticker-notre-window" />
                      <span className="sticker-notre-door" />
                      <span className="sticker-notre-arm sticker-notre-arm-left" />
                      <span className="sticker-notre-arm sticker-notre-arm-right" />
                      <span className="sticker-face-eye sticker-face-eye-left" />
                      <span className="sticker-face-eye sticker-face-eye-right" />
                      <span className="sticker-face-mouth" />
                      <span className="sticker-face-cheek sticker-face-cheek-left" />
                      <span className="sticker-face-cheek sticker-face-cheek-right" />
                    </div>
                    <strong>{copy.landmarkPrompts[1].name}</strong>
                    <p>{copy.landmarkPrompts[1].subtitle}</p>
                  </button>
                </div>
              </div>

              <div className="assistant-tabs" role="tablist" aria-label={copy.tabAria}>
                {copy.guideMessages.map((guide) => (
                  <button
                    key={guide.id}
                    type="button"
                    className={guide.id === activeGuide.id ? "assistant-tab active" : "assistant-tab"}
                    onClick={() => setActiveGuideId(guide.id)}
                  >
                    {guide.label}
                  </button>
                ))}
              </div>

              <div className="assistant-footer">
                <div className="assistant-example-header">
                  <strong>{copy.exampleTitle}</strong>
                  <p>{copy.exampleDescription}</p>
                </div>

                <div className="assistant-examples">
                  {copy.promptExamples.map((example) => (
                    <button key={example.label} type="button" onClick={() => applyPrompt(example.prompt, example.guideId)}>
                      {example.label}
                    </button>
                  ))}
                </div>

                <div className="assistant-style-row">
                  {copy.vibeTags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>

                <div className="scene-actions">
                  <label className="background-uploader">
                    <input type="file" accept="image/*" onChange={(event) => handleBackgroundUpload(event.target.files?.[0])} />
                    {copy.uploadBackground}
                  </label>
                  {heroImage !== DEFAULT_HERO_IMAGE ? (
                    <button type="button" className="background-reset" onClick={handleResetBackground}>
                      {copy.resetBackground}
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
