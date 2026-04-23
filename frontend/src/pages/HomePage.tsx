import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { tripService } from "../services/tripService";
import { useAuth } from "../store/AuthContext";

const DEFAULT_HERO_IMAGE = "/images/paris-default-hero.jpeg";
const promptExamples = ["3박 4일 파리 여행 계획 짜줘", "박물관 위주로 조용한 여행 하고 싶어", "에펠탑 야경이 꼭 포함되게 해줘"];

export function HomePage() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [prompt, setPrompt] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [heroImage, setHeroImage] = useState(localStorage.getItem("parisHeroPhoto") || DEFAULT_HERO_IMAGE);

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
      setError(err instanceof Error ? err.message : "여행 계획 생성 요청에 실패했습니다.");
    } finally {
      setIsGenerating(false);
    }
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
    <main
      className="home-page"
      style={heroImage ? ({ "--hero-image": `url(${heroImage})` } as React.CSSProperties) : undefined}
    >
      <div className="hero-overlay" />
      <section className="hero-content">
        <div className="hero-header">
          <div className="hero-copy">
            <span className="eyebrow light">Paris AI Agent</span>
            <h1>
              <span>파리 여행의 첫 문장을</span>
              <span>입력하세요.</span>
            </h1>
            <p className="hero-description">
              자연어로 취향과 요구사항을 남기면, 웹 서비스가 agent 요청 구조로 전달하고 여행 계획과 사용자 데이터를 안정적으로 저장합니다.
            </p>
          </div>
          <div className="paris-notes" aria-hidden="true">
            <div className="paris-note">
              <span className="paris-note-icon">🗼</span>
              <span>여행 계획 세우러 가볼까?</span>
            </div>
            <div className="paris-note">
              <span className="paris-note-icon">🇫🇷</span>
              <span>오늘의 파리 감성은?</span>
            </div>
            <div className="paris-note">
              <span className="paris-note-icon">⛪</span>
              <span>노트르담 산책도 좋아</span>
            </div>
          </div>
        </div>
        <div className="hero-actions">
          <form className="prompt-box" onSubmit={handleSubmit}>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="예: 에펠탑 야경과 미술관을 포함한 3박 4일 파리 여행 계획 짜줘"
            />
            <button type="submit" className="primary-button" disabled={isGenerating}>
              {isGenerating ? "계획 생성 중..." : "여행 계획 만들기"}
            </button>
          </form>
          {error ? <p className="form-error">{error}</p> : null}
          <div className="prompt-examples">
            {promptExamples.map((example) => (
              <button key={example} type="button" onClick={() => setPrompt(example)}>
                {example}
              </button>
            ))}
          </div>
          {!isAuthenticated ? (
            <p className="hero-login-note">
              여행 데이터를 저장하려면 <Link to="/login">Google 로그인</Link>이 필요합니다.
            </p>
          ) : null}
        </div>
      </section>
      <div className="background-actions">
        <label className="background-uploader">
          <input type="file" accept="image/*" onChange={(event) => handleBackgroundUpload(event.target.files?.[0])} />
          배경 사진 바꾸기
        </label>
        {heroImage !== DEFAULT_HERO_IMAGE ? (
          <button type="button" className="background-reset" onClick={handleResetBackground}>
            기본 파리 사진으로 되돌리기
          </button>
        ) : null}
      </div>
    </main>
  );
}
