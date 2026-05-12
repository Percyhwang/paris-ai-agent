import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../store/AuthContext";
import { useLanguage } from "../../store/LanguageContext";
import { LoadingState } from "./LoadingState";

export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  const { language } = useLanguage();
  const location = useLocation();

  if (isLoading) {
    return <LoadingState label={language === "en" ? "Checking login status..." : "로그인 상태를 확인하는 중입니다"} />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
