import { FormEvent, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link, useNavigate } from "react-router-dom";
import { tripService } from "../services/tripService";
import { useAuth } from "../store/AuthContext";
import { useLanguage } from "../store/LanguageContext";
import type { Trip, TripGenerationJob } from "../types";

const DEFAULT_HERO_IMAGE = "/images/paris-sunset-hero.png";
const GENERATION_POLL_INTERVAL_MS = 2000;
const GENERATION_MAX_POLLS = 180;

type BuilderGroupKey = "style" | "interests" | "time" | "avoid" | "companion" | "budget";
type LanguageKey = "ko" | "en";

type BuilderOption = {
  id: string;
  label: string;
  context: string;
};

type BuilderCluster = {
  label: string;
  optionIds: string[];
};

type BuilderGroup = {
  key: BuilderGroupKey;
  eyebrow: string;
  title: string;
  helper: string;
  options: BuilderOption[];
  clusters?: BuilderCluster[];
};

type BuilderSelections = Record<BuilderGroupKey, string[]>;

type PreviewStep = {
  time: string;
  period: string;
  title: string;
  detail: string;
};

const SINGLE_SELECT_GROUPS = new Set<BuilderGroupKey>(["companion", "budget"]);

function emptySelections(): BuilderSelections {
  return {
    style: [],
    interests: [],
    time: [],
    avoid: [],
    companion: [],
    budget: [],
  };
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function generationStatusLabel(job: TripGenerationJob): string {
  const progress = Math.max(0, Math.min(100, Math.round(job.progress || 0)));
  return `${progress}% - ${job.message || job.stage}`;
}

const HOME_COPY = {
  ko: {
    vibeTags: ["파리 무드", "취향 선택", "AI 일정 설계"],
    heroStatus: "AI Paris Planner",
    kicker: "취향을 고르면 파리 하루가 그려져요",
    titleTop: "파리,",
    titleBottom: "오늘은 어떤 무드로 떠날까요?",
    heroDescription:
      "원하는 분위기와 조건을 고르면 AI Agent가 동선, 시간대, 여행 속도를 맞춰 파리 일정을 설계합니다.",
    tripRequest: "Mood builder",
    requestTitle: "오늘의 파리 무드를 골라주세요.",
    requestDescription: "여행 스타일, 관심사, 시간대, 동행자만 골라도 Agent가 일정 기준으로 해석합니다.",
    requestHint: "취향 고르기",
    memoLabel: "추가 요청",
    memoPlaceholder: "예: 센강 근처에서 저녁 먹고 에펠탑 야경으로 마무리하고 싶어",
    emptyError: "여행 취향을 하나 이상 선택하거나 추가 요청을 입력해주세요.",
    submitError: "여행 플랜을 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.",
    supportLoggedIn: "선택한 취향을 바탕으로 Agent가 일정 생성 후 동선과 조건을 검토합니다.",
    supportLoggedOutPrefix: "로그인하면 생성된 일정과 Agent 검토 결과를 저장할 수 있어요. ",
    supportLoggedOutLink: "Google로 로그인",
    generating: "AI가 파리 일정을 설계 중...",
    generate: "내 파리 일정 만들기",
    freeTextEmpty: "추가 요청 없음",
    moodBoardLabel: "파리 여행 무드보드",
    sideEyebrow: "Paris mood",
    sideTitle: "작은 취향들이 하루의 분위기를 만들어요.",
    sideDescription: "카페, 산책, 야경, 랜드마크를 고르면 Agent가 어울리는 흐름으로 엮어줍니다.",
    sideTicketLead: "Today's mood",
    sideTicketEmpty: "취향을 고르면 여기의 여행 티켓도 함께 채워집니다.",
    sideBadges: ["Seine sunset", "Cafe terrace", "Night sparkle"],
    optionGroups: [
      {
        key: "style",
        eyebrow: "Style",
        title: "여행 스타일",
        helper: "하루의 속도와 감정선을 정합니다.",
        options: [
          { id: "slow", label: "여유롭게", context: "느긋한 pace로 장소 수를 줄이고 휴식 여백을 둔다." },
          { id: "dense", label: "알차게", context: "핵심 명소를 효율적으로 묶되 이동 낭비를 줄인다." },
          { id: "romantic", label: "로맨틱", context: "산책, 석양, 야경, 분위기 좋은 식사 흐름을 우선한다." },
          { id: "local", label: "현지인처럼", context: "유명 관광지만 반복하지 않고 동네 산책과 로컬 장소를 섞는다." },
        ],
      },
      {
        key: "interests",
        eyebrow: "Interests",
        title: "관심사",
        helper: "활동과 명소 성향을 함께 고릅니다.",
        clusters: [
          { label: "활동 관심사", optionIds: ["museum", "cafe", "shopping", "walk", "food"] },
          { label: "관광지 관심", optionIds: ["iconic_sights", "hidden_gems", "viewpoints", "local_spots"] },
        ],
        options: [
          { id: "museum", label: "미술관", context: "미술관 또는 전시 경험을 일정에 포함한다." },
          { id: "cafe", label: "카페", context: "분위기 좋은 카페 휴식 또는 디저트 타임을 포함한다." },
          { id: "shopping", label: "쇼핑", context: "쇼핑 거리나 편집숍을 무리 없는 동선에 배치한다." },
          { id: "walk", label: "산책", context: "센강, 골목, 공원처럼 걷는 경험을 자연스럽게 연결한다." },
          { id: "food", label: "맛집", context: "브런치, 비스트로, 저녁 식사 등 식사 경험을 명확히 배치한다." },
          { id: "iconic_sights", label: "유명 관광지", context: "파리 대표 관광지를 일정에 포함하되 동선이 과하지 않게 묶는다." },
          { id: "hidden_gems", label: "숨은 명소", context: "덜 붐비는 숨은 명소와 작은 골목을 섞는다." },
          { id: "viewpoints", label: "전망 포인트", context: "도시가 잘 보이는 전망대, 다리, 언덕, 강변 포인트를 후보에 포함한다." },
          { id: "local_spots", label: "현지인 감성 스팟", context: "로컬 카페, 동네 산책길, 현지인 감성 장소를 우선한다." },
        ],
      },
      {
        key: "time",
        eyebrow: "Time",
        title: "시간 스타일",
        helper: "하루 시작과 클라이맥스를 정합니다.",
        options: [
          { id: "early_start", label: "아침 일찍", context: "이른 오전부터 움직일 수 있으므로 인기 명소를 오전 앞쪽에 배치한다." },
          { id: "late_start", label: "늦게 시작", context: "오전 일정을 과하게 잡지 않고 늦은 시작을 반영한다." },
          { id: "brunch", label: "브런치 선호", context: "아침 대신 브런치로 하루를 시작하는 흐름을 우선한다." },
          { id: "sunset", label: "석양 보기", context: "sunset 시간대에 전망, 강변, 다리, 공원 중 하나를 배치한다." },
          { id: "night_required", label: "야경 필수", context: "밤 시간대에 대표 야경 장소를 반드시 배치한다." },
        ],
      },
      {
        key: "avoid",
        eyebrow: "Avoid",
        title: "제외 조건",
        helper: "싫어하는 흐름을 미리 막습니다.",
        options: [
          { id: "no_museums", label: "박물관 제외", context: "박물관과 실내 전시 중심 장소를 피한다." },
          { id: "less_walking", label: "많이 걷기 싫음", context: "도보 부담을 낮추고 권역 이동을 최소화한다." },
          { id: "less_touristy", label: "관광지 최소화", context: "대표 관광지만 나열하지 않고 덜 붐비는 장소를 섞는다." },
          { id: "no_expensive", label: "비싼 식당 제외", context: "고가 파인다이닝보다 합리적인 식사 장소를 우선한다." },
        ],
      },
      {
        key: "companion",
        eyebrow: "With",
        title: "동행자",
        helper: "같이 가는 사람에 맞춰 분위기를 조정합니다.",
        options: [
          { id: "solo", label: "혼자", context: "혼자 걷고 쉬기 좋은 안정적인 동선을 만든다." },
          { id: "couple", label: "연인", context: "대화, 산책, 야경, 분위기 좋은 식사를 중심으로 구성한다." },
          { id: "friends", label: "친구", context: "사진, 맛집, 쇼핑, 이동 편의의 균형을 맞춘다." },
          {
            id: "family",
            label: "가족",
            context: "가족 여행으로 해석하고 pace를 조금 느리게 잡으며, 이동 강도와 도보 부담을 낮추고 가족 친화 장소를 우선한다.",
          },
        ],
      },
      {
        key: "budget",
        eyebrow: "Budget",
        title: "예산",
        helper: "식사와 유료 명소의 강도를 맞춥니다.",
        options: [
          { id: "low", label: "가볍게", context: "무료 산책 코스와 합리적인 식사 장소를 우선한다." },
          { id: "mid", label: "중간", context: "유료 명소와 식사 경험을 균형 있게 섞는다." },
          { id: "special", label: "특별하게", context: "하루의 클라이맥스에 특별한 식사나 전망 경험을 넣는다." },
        ],
      },
    ] satisfies BuilderGroup[],
  },
  en: {
    vibeTags: ["Paris mood", "Pick your taste", "AI route design"],
    heroStatus: "AI Paris Planner",
    kicker: "Pick a mood and let Paris take shape",
    titleTop: "Paris,",
    titleBottom: "planned around your mood.",
    heroDescription:
      "Choose the atmosphere and conditions you want. The AI Agent shapes timing, route flow, and pace into a Paris itinerary.",
    tripRequest: "Mood builder",
    requestTitle: "Choose today's Paris mood.",
    requestDescription: "Style, interests, timing, and companion choices are enough for the Agent to understand your trip.",
    requestHint: "Pick your mood",
    memoLabel: "Additional request",
    memoPlaceholder: "Example: Have dinner near the Seine and finish with the Eiffel Tower night view.",
    emptyError: "Choose at least one preference or write an additional request.",
    submitError: "Something went wrong while building your trip plan. Please try again shortly.",
    supportLoggedIn: "The Agent will generate the itinerary and review route flow and constraints.",
    supportLoggedOutPrefix: "Sign in to save the generated itinerary and Agent review. ",
    supportLoggedOutLink: "Sign in with Google",
    generating: "AI is designing your Paris day...",
    generate: "Create My Paris Plan",
    freeTextEmpty: "No additional request",
    moodBoardLabel: "Paris travel mood board",
    sideEyebrow: "Paris mood",
    sideTitle: "Small preferences become the feeling of the day.",
    sideDescription: "Pick cafes, walks, night views, and landmarks. The Agent will tie them into a natural route.",
    sideTicketLead: "Today's mood",
    sideTicketEmpty: "Your travel ticket fills in as you choose preferences.",
    sideBadges: ["Seine sunset", "Cafe terrace", "Night sparkle"],
    optionGroups: [
      {
        key: "style",
        eyebrow: "Style",
        title: "Travel style",
        helper: "Sets the rhythm and emotional arc of the day.",
        options: [
          { id: "slow", label: "Slow", context: "Keep the pace relaxed with fewer stops and enough breathing room." },
          { id: "dense", label: "Full", context: "Group key places efficiently while avoiding wasted transfers." },
          { id: "romantic", label: "Romantic", context: "Prioritize walks, sunset, night views, and atmospheric meals." },
          { id: "local", label: "Like a local", context: "Mix local neighborhoods with fewer obvious tourist-only choices." },
        ],
      },
      {
        key: "interests",
        eyebrow: "Interests",
        title: "Interests",
        helper: "Choose activities and sightseeing preferences together.",
        clusters: [
          { label: "Activities", optionIds: ["museum", "cafe", "shopping", "walk", "food"] },
          { label: "Sightseeing", optionIds: ["iconic_sights", "hidden_gems", "viewpoints", "local_spots"] },
        ],
        options: [
          { id: "museum", label: "Museums", context: "Include museum or exhibition experiences." },
          { id: "cafe", label: "Cafes", context: "Include a charming cafe or dessert break." },
          { id: "shopping", label: "Shopping", context: "Place shopping streets or boutiques inside a sensible route." },
          { id: "walk", label: "Walks", context: "Connect river, street, and park walks naturally." },
          { id: "food", label: "Food", context: "Make brunch, bistro, or dinner moments explicit in the day." },
          { id: "iconic_sights", label: "Famous sights", context: "Include iconic Paris sights without overloading the route." },
          { id: "hidden_gems", label: "Hidden gems", context: "Mix less crowded places and small side streets." },
          { id: "viewpoints", label: "Viewpoints", context: "Include viewpoints, bridges, hills, or riverside spots with a strong city view." },
          { id: "local_spots", label: "Local-feel spots", context: "Prioritize local cafes, neighborhood walks, and local-feel places." },
        ],
      },
      {
        key: "time",
        eyebrow: "Time",
        title: "Time style",
        helper: "Sets the start and climax of the day.",
        options: [
          { id: "early_start", label: "Early start", context: "Start early and place popular sights in the first morning slots." },
          { id: "late_start", label: "Late start", context: "Avoid an overloaded morning and respect a later start." },
          { id: "brunch", label: "Prefer brunch", context: "Prefer a brunch-led start instead of a heavy morning." },
          { id: "sunset", label: "See sunset", context: "Place a scenic bridge, river, park, or viewpoint near sunset." },
          { id: "night_required", label: "Night view required", context: "Include a signature night-view stop at night." },
        ],
      },
      {
        key: "avoid",
        eyebrow: "Avoid",
        title: "Avoid",
        helper: "Tell the Agent what to keep out.",
        options: [
          { id: "no_museums", label: "No museums", context: "Avoid museum-heavy or indoor exhibition-focused stops." },
          { id: "less_walking", label: "Less walking", context: "Reduce walking load and keep neighborhoods clustered." },
          { id: "less_touristy", label: "Fewer tourist spots", context: "Avoid simply listing major tourist landmarks." },
          { id: "no_expensive", label: "No expensive restaurants", context: "Prefer reasonable meals over fine dining." },
        ],
      },
      {
        key: "companion",
        eyebrow: "With",
        title: "Companion",
        helper: "Tunes the route for who is traveling.",
        options: [
          { id: "solo", label: "Solo", context: "Build a calm route that feels comfortable alone." },
          { id: "couple", label: "Couple", context: "Center conversation, walking, night views, and atmospheric meals." },
          { id: "friends", label: "Friends", context: "Balance photos, food, shopping, and convenient transfers." },
          {
            id: "family",
            label: "Family",
            context: "Treat this as a family trip: slow the pace slightly, lower transfer and walking intensity, and prioritize family-friendly places.",
          },
        ],
      },
      {
        key: "budget",
        eyebrow: "Budget",
        title: "Budget",
        helper: "Sets the intensity of paid stops and meals.",
        options: [
          { id: "low", label: "Light", context: "Prefer free walks and reasonable meals." },
          { id: "mid", label: "Medium", context: "Balance paid sights with everyday food choices." },
          { id: "special", label: "Special", context: "Add one memorable meal or scenic experience as the climax." },
        ],
      },
    ] satisfies BuilderGroup[],
  },
} as const;

function selectedOptionsForGroup(group: BuilderGroup, selections: BuilderSelections): BuilderOption[] {
  const selectedIds = new Set(selections[group.key]);
  return group.options.filter((option) => selectedIds.has(option.id));
}

function hasAny(selectedIds: Set<string>, ids: string[]): boolean {
  return ids.some((id) => selectedIds.has(id));
}

function buildPreviewSteps(selectedIds: Set<string>, language: LanguageKey): PreviewStep[] {
  const isEnglish = language === "en";
  const earlyStart = hasAny(selectedIds, ["early_start"]);
  const slowStart = hasAny(selectedIds, ["slow", "late_start", "brunch", "family"]);
  const sightFocus = hasAny(selectedIds, ["iconic_sights", "viewpoints", "museum"]);
  const localFocus = hasAny(selectedIds, ["local", "hidden_gems", "local_spots"]);
  const nightFocus = hasAny(selectedIds, ["night", "night_required", "romantic"]);
  const foodFocus = hasAny(selectedIds, ["food", "special"]);

  return [
    {
      time: earlyStart ? "08:30" : slowStart ? "10:30" : "09:30",
      period: isEnglish ? "Morning" : "Morning",
      title: isEnglish
        ? earlyStart
          ? "Start early with a calm first landmark"
          : slowStart
          ? "Start slowly with brunch or coffee"
          : "Start with one clear anchor"
        : earlyStart
          ? "아침 일찍 첫 명소부터 가볍게 시작"
          : slowStart
          ? "브런치나 카페로 천천히 시작"
          : "첫 목적지를 가볍게 잡고 시작",
      detail: isEnglish
        ? earlyStart
          ? "The Agent uses the quieter morning window for popular places."
          : "The Agent keeps the first stop comfortable before the route gets busier."
        : earlyStart
          ? "붐비기 전 오전 시간대를 활용해 인기 명소를 앞쪽에 둬요."
          : "초반부터 무리하지 않도록 첫 동선을 편하게 잡아요.",
    },
    {
      time: "14:30",
      period: isEnglish ? "Afternoon" : "Afternoon",
      title: isEnglish
        ? sightFocus
          ? "Landmarks without route clutter"
          : localFocus
            ? "Neighborhood walks and local-feel spots"
            : "A walkable Paris neighborhood flow"
        : sightFocus
          ? "랜드마크를 무리 없는 동선으로 연결"
          : localFocus
            ? "동네 골목과 현지 감성 스팟 산책"
            : "걷기 좋은 파리 권역으로 연결",
      detail: isEnglish
        ? "Nearby places are grouped so the day feels planned, not scattered."
        : "같은 권역을 묶어서 흩어진 추천처럼 보이지 않게 정리해요.",
    },
    {
      time: nightFocus ? "20:00" : foodFocus ? "19:00" : "18:30",
      period: isEnglish ? "Evening" : "Evening",
      title: isEnglish
        ? nightFocus
          ? "Finish with a night-view moment"
          : foodFocus
            ? "Close with dinner as the highlight"
            : "End with a calm Seine-side finish"
        : nightFocus
          ? "야경으로 하루를 마무리"
          : foodFocus
            ? "저녁 식사를 하이라이트로 마무리"
            : "센강 근처에서 차분하게 마무리",
      detail: isEnglish
        ? "The final stop becomes the emotional peak instead of another random place."
        : "마지막 장소가 단순 추가가 아니라 하루의 클라이맥스가 되게 잡아요.",
    },
  ];
}

export function HomePage() {
  const navigate = useNavigate();
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const { isAuthenticated } = useAuth();
  const { language } = useLanguage();
  const copy = HOME_COPY[(language as LanguageKey) || "ko"] ?? HOME_COPY.ko;
  const [prompt, setPrompt] = useState("");
  const [selections, setSelections] = useState<BuilderSelections>(() => emptySelections());
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStatus, setGenerationStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedGroups = useMemo(
    () =>
      copy.optionGroups
        .map((group) => ({
          group,
          options: selectedOptionsForGroup(group, selections),
        }))
        .filter((item) => item.options.length > 0),
    [copy.optionGroups, selections],
  );

  const selectedLabels = useMemo(() => selectedGroups.flatMap((item) => item.options.map((option) => option.label)), [selectedGroups]);

  const selectedContextLines = useMemo(
    () =>
      selectedGroups.map((item) => {
        const labels = item.options.map((option) => option.label).join(", ");
        return `${item.group.title}: ${labels}`;
      }),
    [selectedGroups],
  );

  const planningContext = useMemo(() => {
    const ruleLines = selectedGroups.flatMap((item) => item.options.map((option) => `- ${option.context}`));
    const freeText = prompt.trim();
    if (selectedContextLines.length === 0 && !freeText) return "";

    const userRequestLabel = language === "en" ? "Additional user request" : "사용자 추가 요청";
    const instruction =
      language === "en"
        ? "Use these as user constraints. Generate a Paris itinerary, evaluate it, fix issues if needed, and return only the reviewed final plan."
        : "이 조건을 사용자 제약으로 사용해 파리 일정을 만들고, 생성 후 평가하고, 문제가 있으면 수정한 최종 일정만 반환해줘.";

    return [
      "[Planning Context]",
      ...selectedContextLines,
      "",
      "[Agent planning rules]",
      ...ruleLines,
      "",
      `[${userRequestLabel}]`,
      freeText || copy.freeTextEmpty,
      "",
      "[Agent instruction]",
      instruction,
    ].join("\n");
  }, [copy.freeTextEmpty, language, prompt, selectedContextLines, selectedGroups]);

  const heroImage = localStorage.getItem("parisHeroPhoto") || DEFAULT_HERO_IMAGE;
  const heroStyle = heroImage ? ({ "--hero-image": `url(${heroImage})` } as CSSProperties) : undefined;
  const canSubmit = Boolean(planningContext.trim());
  const selectedIds = useMemo(() => new Set(Object.values(selections).flat()), [selections]);
  const previewSteps = useMemo(() => buildPreviewSteps(selectedIds, (language as LanguageKey) || "ko"), [language, selectedIds]);
  const previewTags =
    selectedLabels.length > 0
      ? selectedLabels.slice(0, 6)
      : language === "en"
        ? ["Slow pace", "Cafe", "Seine walk", "Night view"]
        : ["여유롭게", "카페", "센강 산책", "야경"];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) {
      setError(copy.emptyError);
      return;
    }

    if (!isAuthenticated) {
      navigate("/login", { state: { from: { pathname: "/" } } });
      return;
    }

    setIsGenerating(true);
    setGenerationStatus(null);
    setError(null);
    try {
      const startedJob = await tripService.startTripGeneration({
        prompt: planningContext.trim(),
        style_tags: selectedLabels,
      });
      setGenerationStatus(generationStatusLabel(startedJob));
      const trip = await waitForTripGeneration(startedJob.job_id);
      navigate(`/trips/${trip.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : copy.submitError);
    } finally {
      setIsGenerating(false);
      setGenerationStatus(null);
    }
  }

  async function waitForTripGeneration(jobId: string): Promise<Trip> {
    for (let attempt = 0; attempt < GENERATION_MAX_POLLS; attempt += 1) {
      await delay(attempt === 0 ? 500 : GENERATION_POLL_INTERVAL_MS);
      const job = await tripService.getTripGenerationJob(jobId);
      setGenerationStatus(generationStatusLabel(job));

      if (job.status === "completed") {
        if (job.trip) return job.trip;
        if (job.trip_id) return tripService.getTrip(job.trip_id);
        throw new Error("Trip generation completed without a trip id.");
      }

      if (job.status === "failed") {
        throw new Error(job.error || "Trip generation failed.");
      }
    }

    throw new Error("Trip generation is still running. Please check your trips again shortly.");
  }

  function toggleOption(group: BuilderGroup, optionId: string) {
    setError(null);
    setSelections((current) => {
      const existing = current[group.key];
      const isActive = existing.includes(optionId);
      const nextForGroup = SINGLE_SELECT_GROUPS.has(group.key)
        ? isActive
          ? []
          : [optionId]
        : isActive
          ? existing.filter((id) => id !== optionId)
          : [...existing, optionId];

      return {
        ...current,
        [group.key]: nextForGroup,
      };
    });
  }

  function clearBuilder() {
    setSelections(emptySelections());
    setPrompt("");
    setError(null);
  }

  return (
    <main className="home-page" style={heroStyle}>
      <div className="hero-overlay" />
      <section className="hero-content home-agent-content">
        <div className="hero-grid agent-builder-grid">
          <div className="hero-main-column">
            <div className="hero-intro agent-hero-intro">
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
              <div className="hero-mini-chips" aria-label="agent features">
                {copy.vibeTags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </div>

            <form className="conversation-panel agent-builder-panel" onSubmit={handleSubmit}>
              <div className="conversation-head">
                <div className="conversation-copy">
                  <span className="prompt-panel-eyebrow">{copy.tripRequest}</span>
                  <h2>{copy.requestTitle}</h2>
                  <p>{copy.requestDescription}</p>
                </div>
                <span className="conversation-hint">{copy.requestHint}</span>
              </div>

              <div className="preference-builder">
                {copy.optionGroups.map((group) => {
                  const optionById = new Map(group.options.map((option) => [option.id, option]));
                  const clusters = group.clusters ?? [{ label: "", optionIds: group.options.map((option) => option.id) }];
                  return (
                    <section className="preference-section" key={group.key}>
                      <div className="preference-section-head">
                        <span>{group.eyebrow}</span>
                        <div>
                          <h3>{group.title}</h3>
                          <p>{group.helper}</p>
                        </div>
                      </div>
                      <div className="preference-cluster-list">
                        {clusters.map((cluster) => (
                          <div className="preference-cluster" key={`${group.key}-${cluster.label || "default"}`}>
                            {cluster.label ? <span className="preference-cluster-label">{cluster.label}</span> : null}
                            <div className="preference-chip-grid">
                              {cluster.optionIds.map((optionId) => {
                                const option = optionById.get(optionId);
                                if (!option) return null;
                                const isActive = selections[group.key].includes(option.id);
                                return (
                                  <button
                                    type="button"
                                    key={option.id}
                                    className={isActive ? "preference-chip active" : "preference-chip"}
                                    aria-pressed={isActive}
                                    onClick={() => toggleOption(group, option.id)}
                                  >
                                    {option.label}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>

              <label className="agent-note-field" htmlFor="trip-request">
                <span>{copy.memoLabel}</span>
                <textarea
                  ref={promptRef}
                  id="trip-request"
                  className="conversation-textarea"
                  value={prompt}
                  onChange={(event) => {
                    setPrompt(event.target.value);
                    setError(null);
                  }}
                  placeholder={copy.memoPlaceholder}
                />
              </label>

              {error ? <p className="form-error hero-form-error">{error}</p> : null}
              {generationStatus ? (
                <div className="generation-status" role="status" aria-live="polite">
                  <span className="generation-spinner" aria-hidden="true" />
                  <span>{generationStatus}</span>
                </div>
              ) : null}

              <div className="conversation-foot agent-builder-foot">
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
                <div className="agent-builder-actions">
                  <button type="button" className="secondary-button builder-clear-button" onClick={clearBuilder}>
                    Reset
                  </button>
                  <button type="submit" className="primary-button prompt-submit-button" disabled={isGenerating || !canSubmit}>
                    {isGenerating ? copy.generating : copy.generate}
                  </button>
                </div>
              </div>
            </form>
          </div>

          <aside className="hero-side-panel paris-preview-column">
            <section className="trip-preview-card" aria-label={language === "en" ? "AI trip preview" : "AI 여행 미리보기"}>
              <div className="trip-preview-hero">
                <div className="preview-hero-copy">
                  <span className="eyebrow">{language === "en" ? "AI trip preview" : "AI Trip Preview"}</span>
                  <h3>{language === "en" ? "Your Paris day starts to take shape." : "오늘의 파리 흐름이 이렇게 잡혀요."}</h3>
                  <p>
                    {language === "en"
                      ? "Pick preferences on the left and the Agent turns them into a route rhythm."
                      : "왼쪽에서 취향을 고르면 Agent가 시간대와 동선을 맞춰 하루 흐름으로 바꿔요."}
                  </p>
                </div>
                <div className="preview-postcard" aria-hidden="true">
                  <span className="preview-sun" />
                  <span className="preview-tower" />
                  <span className="preview-river" />
                </div>
              </div>

              <div className="preview-tag-row" aria-label={language === "en" ? "Selected mood tags" : "선택한 여행 무드"}>
                {previewTags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>

              <div className="preview-flow-list">
                {previewSteps.map((step) => (
                  <article className="preview-flow-item" key={`${step.time}-${step.title}`}>
                    <div className="preview-flow-time">
                      <strong>{step.time}</strong>
                      <span>{step.period}</span>
                    </div>
                    <div className="preview-flow-body">
                      <h4>{step.title}</h4>
                      <p>{step.detail}</p>
                    </div>
                  </article>
                ))}
              </div>

              <div className="preview-agent-note">
                <span>{language === "en" ? "Agent check" : "Agent check"}</span>
                <p>
                  {language === "en"
                    ? "After generation, the Agent reviews route flow, duplicates, timing, and your selected constraints."
                    : "생성 후에는 동선, 중복 장소, 시간대, 선택 조건 반영 여부를 다시 확인해요."}
                </p>
              </div>
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}
