import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../store/AuthContext";
import { HomeLogo } from "./HomeLogo";

const navItems = [
  { to: "/places", label: "파리 스팟" },
  { to: "/trip-plan", label: "여행 플랜" },
  { to: "/reservations", label: "예약 체크" },
  { to: "/budget", label: "예산" },
  { to: "/diary", label: "여행 기록" },
  { to: "/weather", label: "파리 날씨" },
];

export function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

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
        {isAuthenticated && user ? (
          <>
            {user.profile_image ? <img src={user.profile_image} alt={user.name} /> : <span className="avatar-fallback">{avatarFallback}</span>}
            <span>{user.name}</span>
            <button type="button" className="ghost-button small" onClick={handleLogout}>
              로그아웃
            </button>
          </>
        ) : (
          <NavLink to="/login" className="login-pill">
            로그인
          </NavLink>
        )}
      </div>
    </nav>
  );
}
