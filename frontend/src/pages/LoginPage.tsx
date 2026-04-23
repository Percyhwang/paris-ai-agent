import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Card } from "../components/common/Card";
import { useAuth } from "../store/AuthContext";

type LoginLocationState = {
  from?: {
    pathname: string;
  };
};

export function LoginPage() {
  const googleButtonRef = useRef<HTMLDivElement>(null);
  const { loginWithGoogle, demoLogin, isAuthenticated } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LoginLocationState | null)?.from?.pathname ?? "/";
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

  useEffect(() => {
    if (isAuthenticated) navigate(from, { replace: true });
  }, [isAuthenticated, navigate, from]);

  useEffect(() => {
    if (!googleClientId || !googleButtonRef.current) return;

    function renderGoogleButton() {
      if (!window.google || !googleButtonRef.current) return;
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: async (response) => {
          await handleGoogleCredential(response.credential);
        },
      });
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "continue_with",
        locale: "ko",
      });
    }

    if (window.google) {
      renderGoogleButton();
      return;
    }

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = renderGoogleButton;
    document.body.appendChild(script);
  }, [googleClientId]);

  async function handleGoogleCredential(credential: string) {
    setIsSubmitting(true);
    setError(null);
    try {
      await loginWithGoogle(credential);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google 로그인에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDemoLogin() {
    setIsSubmitting(true);
    setError(null);
    try {
      await demoLogin();
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "데모 로그인에 실패했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <Card className="auth-card">
        <span className="eyebrow">Google OAuth</span>
        <h1>파리 여행 데이터를 안전하게 저장하세요.</h1>
        <p>Google 계정으로 로그인하면 여행 계획, 예산, 다이어리 데이터를 MongoDB에 사용자별로 저장합니다.</p>
        <div className="google-button-wrap" ref={googleButtonRef}>
          {!googleClientId ? <span>Google Client ID를 설정하면 실제 로그인 버튼이 표시됩니다.</span> : null}
        </div>
        <button type="button" className="primary-button full-width" onClick={handleDemoLogin} disabled={isSubmitting}>
          로컬 데모 계정으로 시작
        </button>
        {error ? <p className="form-error">{error}</p> : null}
        <Link to="/" className="text-link">
          홈으로 돌아가기
        </Link>
      </Card>
    </main>
  );
}
