import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LoadingState } from "./LoadingState";
import { useAuth } from "../../store/AuthContext";

export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingState label="로그인 상태를 확인하는 중입니다" />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
