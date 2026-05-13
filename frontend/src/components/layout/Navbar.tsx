import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../store/AuthContext";
import { useLanguage } from "../../store/LanguageContext";
import { HomeLogo } from "./HomeLogo";

const NAV_LABELS = {
  ko: {
    places: "파리 스팟",
    tripPlan: "여행 플랜",
    accommodations: "숙소 검색",
    flights: "항공권 검색",
    budget: "예산",
    diary: "여행 기록",
    weather: "파리 날씨",
    login: "로그인",
    logout: "로그아웃",
    language: "언어 선택",
  },
  en: {
    places: "Paris Spots",
    tripPlan: "Trip Plan",
    accommodations: "Stays",
    flights: "Flights",
    budget: "Budget",
    diary: "Diary",
    weather: "Weather",
    login: "Log In",
    logout: "Log Out",
    language: "Language",
  },
} as const;

export function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const { language, setLanguage } = useLanguage();
  const navigate = useNavigate();
  const copy = NAV_LABELS[language];

  const navItems = [
    { to: "/places", label: copy.places },
    { to: "/trip-plan", label: copy.tripPlan },
    { to: "/accommodations", label: copy.accommodations },
    { to: "/flights", label: copy.flights },
    { to: "/budget", label: copy.budget },
    { to: "/diary", label: copy.diary },
    { to: "/weather", label: copy.weather },
  ];

  function handleLogout() {
    logout();
    navigate("/");
  }

  const avatarFallback = user?.name?.trim()?.charAt(0)?.toUpperCase() || "P";

  return (
    <nav className="navbar">
      <HomeLogo />
      <div className="nav-links">
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? "active" : undefined)}>
            {item.label}
          </NavLink>
        ))}
      </div>
      <div className="nav-user">
        <div className="language-switch" role="group" aria-label={copy.language}>
          <button type="button" className={language === "ko" ? "active" : undefined} onClick={() => void setLanguage("ko")}>
            KO
          </button>
          <button type="button" className={language === "en" ? "active" : undefined} onClick={() => void setLanguage("en")}>
            EN
          </button>
        </div>
        {isAuthenticated && user ? (
          <>
            {user.profile_image ? <img src={user.profile_image} alt={user.name} /> : <span className="avatar-fallback">{avatarFallback}</span>}
            <span>{user.name}</span>
            <button type="button" className="ghost-button small" onClick={handleLogout}>
              {copy.logout}
            </button>
          </>
        ) : (
          <NavLink to="/login" className="login-pill">
            {copy.login}
          </NavLink>
        )}
      </div>
    </nav>
  );
}
