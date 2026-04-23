import { FormEvent, useRef, useState, type CSSProperties } from "react";
import { Link, useNavigate } from "react-router-dom";
import { tripService } from "../services/tripService";
import { useAuth } from "../store/AuthContext";

const DEFAULT_HERO_IMAGE = "/images/paris-sunset-hero.png";

const vibeTags = ["낭만적인 파리", "미식 중심 파리", "여유로운 산책 파리"];

const guideMessages = [
  {
    id: "mood",
    label: "감성",
    title: "어떤 분위기의 파리를 원하세요?",
    description: "감성 카페, 미술관, 야경 코스로도 가볍게 짜드릴게요.",
  },
  {
    id: "pace",
    label: "동선",
    title: "짧게 적어도 충분해요 :)",
    description: "천천히 걷고 싶은지, 하루를 꽉 채우고 싶은지만 알려주셔도 좋아요.",
  },
  {
    id: "budget",
    label: "예산",
    title: "취향과 예산도 같이 맞춰드릴게요.",
    description: "가볍게 즐기는 일정부터 특별한 하루까지, 분위기에 맞게 정리해드려요.",
  },
];

const promptExamples = [
  {
    label: "미술관 + 야경",
    guideId: "mood",
    prompt: "루브르와 오르세를 여유롭게 보고, 마지막 밤에는 센강 야경까지 담은 3박 4일 파리 일정 짜줘",
  },
  {
    label: "카페 + 산책",
    guideId: "pace",
    prompt: "감성 카페와 예쁜 골목 산책이 많은 여유로운 파리 2박 3일 코스 추천해줘",
  },
  {
    label: "미식 주말",
    guideId: "budget",
    prompt: "브런치와 디너를 중심으로 분위기 좋은 곳을 묶은 파리 주말 일정 추천해줘",
  },
];

const landmarkPrompts = [
  {
    id: "eiffel",
    name: "에펠탑",
    subtitle: "반짝 야경 친구",
    guideId: "mood",
    prompt: "에펠탑 야경과 센강 산책이 들어간 낭만적인 파리 일정 추천해줘",
  },
  {
    id: "notre-dame",
    name: "노트르담",
    subtitle: "고즈넉 산책 친구",
    guideId: "pace",
    prompt: "노트르담 주변 산책과 예쁜 골목이 어울리는 여유로운 파리 일정 추천해줘",
  },
];

export function HomePage() {
  const navigate = useNavigate();
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const { isAuthenticated } = useAuth();
  const [prompt, setPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeGuideId, setActiveGuideId] = useState(guideMessages[0].id);
  const [heroImage, setHeroImage] = useState(localStorage.getItem("parisHeroPhoto") || DEFAULT_HERO_IMAGE);

  const activeGuide = guideMessages.find((item) => item.id === activeGuideId) ?? guideMessages[0];
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
      setError(err instanceof Error ? err.message : "여행 플랜을 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.");
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
                <span className="hero-status-pill">Paris mood planner</span>
              </div>
              <div className="hero-headline-stack">
                <p className="hero-kicker">원하는 분위기를 들려주세요.</p>
                <h1>
                  <span>파리, 취향대로</span>
                  <span>떠나볼까요?</span>
                </h1>
                <p className="hero-description">
                  가고 싶은 분위기만 말해주시면 돼요. 취향에 맞는 일정과 예산을 바로 추천해드릴게요.
                </p>
              </div>
              <div className="hero-mini-chips" aria-label="travel styles">
                {vibeTags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </div>

            <form className="conversation-panel" onSubmit={handleSubmit}>
              <div className="conversation-head">
                <div className="conversation-copy">
                  <span className="prompt-panel-eyebrow">Trip request</span>
                  <h2>가고 싶은 분위기만 말해주시면 돼요.</h2>
                  <p>한 문장, 몇 개의 키워드, 짧은 메모도 괜찮아요.</p>
                </div>
                <span className="conversation-hint">1문장부터 시작</span>
              </div>

              <div className="conversation-thread">
                <div className="assistant-inline-message">
                  <span className="assistant-inline-avatar">PA</span>
                  <div className="assistant-inline-bubble">
                    <strong>짧게 적어도 괜찮아요 :)</strong>
                    <p>미술관, 야경, 카페처럼 떠오르는 단어만 적어도 충분해요.</p>
                  </div>
                </div>

                <label className="composer-row" htmlFor="trip-request">
                  <span className="composer-avatar">나</span>
                  <div className="composer-shell">
                    <span className="composer-label">나의 여행 메모</span>
                    <textarea
                      ref={promptRef}
                      id="trip-request"
                      className="conversation-textarea"
                      value={prompt}
                      onChange={(event) => setPrompt(event.target.value)}
                      placeholder="예: 여유로운 산책과 미술관, 마지막 밤의 야경이 있는 파리 3박 4일 일정 추천해줘"
                    />
                  </div>
                </label>
              </div>

              {error ? <p className="form-error hero-form-error">{error}</p> : null}

              <div className="conversation-foot">
                <p className="prompt-support-note">
                  {isAuthenticated ? (
                    "입력한 문장으로 바로 일정 초안을 만들어드릴게요."
                  ) : (
                    <>
                      로그인하면 일정, 예산, 예약, 기록까지 이어서 관리돼요. <Link to="/login">Google로 로그인</Link>
                    </>
                  )}
                </p>
                <button type="submit" className="primary-button prompt-submit-button" disabled={isGenerating}>
                  {isGenerating ? "일정 만드는 중..." : "내 여행 만들기"}
                </button>
              </div>
            </form>
          </div>

          <aside className="hero-side-panel">
            <div className="mascot-card">
              <div className="mascot-header">
                <span className="eyebrow">Paris guide</span>
                <h3>귀여운 파리 가이드가 같이 도와드릴게요.</h3>
              </div>

              <div className="mascot-scene">
                <div className="assistant-bubble-card">
                  <span className="assistant-bubble-eyebrow">Paris friends</span>
                  <strong>계획 짜보러 가볼까?</strong>
                  <p>{activeGuide.description}</p>
                </div>

                <div className="paris-sticker-row" aria-label="Paris landmark stickers">
                  <button
                    type="button"
                    className="paris-sticker eiffel-sticker"
                    onClick={() => applyPrompt(landmarkPrompts[0].prompt, landmarkPrompts[0].guideId)}
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
                    <strong>{landmarkPrompts[0].name}</strong>
                    <p>{landmarkPrompts[0].subtitle}</p>
                  </button>

                  <button
                    type="button"
                    className="paris-sticker notre-dame-sticker"
                    onClick={() => applyPrompt(landmarkPrompts[1].prompt, landmarkPrompts[1].guideId)}
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
                    <strong>{landmarkPrompts[1].name}</strong>
                    <p>{landmarkPrompts[1].subtitle}</p>
                  </button>
                </div>
              </div>

              <div className="assistant-tabs" role="tablist" aria-label="guide messages">
                {guideMessages.map((guide) => (
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
                  <strong>예시로 바로 써보기</strong>
                  <p>누르면 입력창에 바로 들어가요.</p>
                </div>

                <div className="assistant-examples">
                  {promptExamples.map((example) => (
                    <button key={example.label} type="button" onClick={() => applyPrompt(example.prompt, example.guideId)}>
                      {example.label}
                    </button>
                  ))}
                </div>

                <div className="assistant-style-row">
                  {vibeTags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>

                <div className="scene-actions">
                  <label className="background-uploader">
                    <input type="file" accept="image/*" onChange={(event) => handleBackgroundUpload(event.target.files?.[0])} />
                    배경 바꾸기
                  </label>
                  {heroImage !== DEFAULT_HERO_IMAGE ? (
                    <button type="button" className="background-reset" onClick={handleResetBackground}>
                      기본 배경
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
