import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Card } from "../components/common/Card";
import { getGoogleLocale } from "../i18n/config";
import { useAuth } from "../store/AuthContext";
import { useLanguage } from "../store/LanguageContext";

type LoginLocationState = {
  from?: {
    pathname: string;
  };
};

const GOOGLE_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

let googleInitializedClientId: string | null = null;
let activeGoogleCredentialHandler: ((credential: string) => Promise<void> | void) | null = null;

const LOGIN_COPY = {
  ko: {
    eyebrow: "Google OAuth",
    title: "파리 여행 데이터를 안전하게 보관해요.",
    description: "Google 계정으로 로그인하면 여행 계획, 예산, 예약, 다이어리 데이터를 계정과 함께 저장할 수 있습니다.",
    missingClientId: "`VITE_GOOGLE_CLIENT_ID`를 설정하면 실제 Google 로그인 버튼이 표시됩니다.",
    originBlocked:
      "현재 주소에서는 Google 로그인이 비활성화되어 있습니다. `VITE_GOOGLE_ALLOWED_ORIGINS`와 Google Cloud Console의 Authorized JavaScript origins를 확인해 주세요.",
    scriptError: "Google 로그인 스크립트를 불러오지 못했습니다. 브라우저 확장 프로그램이나 네트워크를 확인해 주세요.",
    loginFailed: "Google 로그인에 실패했습니다.",
    demoFailed: "데모 로그인에 실패했습니다.",
    demoButton: "데모 계정으로 시작",
    backHome: "홈으로 돌아가기",
  },
  en: {
    eyebrow: "Google OAuth",
    title: "Keep your Paris travel data safely in one place.",
    description: "Sign in with Google to save your trip plans, budget, reservations, and diary to your account.",
    missingClientId: "Set `VITE_GOOGLE_CLIENT_ID` to show the real Google sign-in button.",
    originBlocked:
      "Google sign-in is disabled on this origin. Check `VITE_GOOGLE_ALLOWED_ORIGINS` and the Authorized JavaScript origins in Google Cloud Console.",
    scriptError: "The Google sign-in script could not be loaded. Please check your browser extensions or network.",
    loginFailed: "Google sign-in failed.",
    demoFailed: "Demo sign-in failed.",
    demoButton: "Continue with Demo Account",
    backHome: "Back to Home",
  },
} as const;

function getFriendlyLoginError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  if (error.message === "Database unavailable") {
    return fallback;
  }
  if (error.message === "Invalid Google credential") {
    return fallback;
  }
  return error.message;
}

export function LoginPage() {
  const googleButtonRef = useRef<HTMLDivElement>(null);
  const { loginWithGoogle, demoLogin, isAuthenticated } = useAuth();
  const { language } = useLanguage();
  const copy = LOGIN_COPY[language];
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LoginLocationState | null)?.from?.pathname ?? "/";
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  const googleAllowedOrigins = (import.meta.env.VITE_GOOGLE_ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean);
  const currentOrigin = window.location.origin;
  const isGoogleOriginAllowed = googleAllowedOrigins.length === 0 || googleAllowedOrigins.includes(currentOrigin);

  useEffect(() => {
    activeGoogleCredentialHandler = handleGoogleCredential;
    return () => {
      if (activeGoogleCredentialHandler === handleGoogleCredential) {
        activeGoogleCredentialHandler = null;
      }
    };
  });

  useEffect(() => {
    if (isAuthenticated) navigate(from, { replace: true });
  }, [isAuthenticated, navigate, from]);

  useEffect(() => {
    if (!googleClientId || !googleButtonRef.current || !isGoogleOriginAllowed) return;
    const clientId = googleClientId;

    function renderGoogleButton() {
      if (!window.google || !googleButtonRef.current) return;
      googleButtonRef.current.replaceChildren();
      try {
        if (googleInitializedClientId !== clientId) {
          window.google.accounts.id.initialize({
            client_id: clientId,
            callback: (response) => {
              if (!response.credential) {
                setError(copy.loginFailed);
                return;
              }
              void activeGoogleCredentialHandler?.(response.credential);
            },
            ux_mode: "popup",
            auto_select: false,
            itp_support: true,
          });
          googleInitializedClientId = clientId;
        }
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          theme: "outline",
          size: "large",
          shape: "pill",
          text: "continue_with",
          locale: getGoogleLocale(language),
        });
      } catch {
        setError(copy.originBlocked);
      }
    }

    if (window.google) {
      renderGoogleButton();
      return;
    }

    const existingScript = document.querySelector<HTMLScriptElement>(`script[src="${GOOGLE_SCRIPT_SRC}"]`);
    const handleScriptError = () => {
      setError(copy.scriptError);
    };

    if (existingScript) {
      existingScript.addEventListener("load", renderGoogleButton, { once: true });
      existingScript.addEventListener("error", handleScriptError, { once: true });
      return () => {
        existingScript.removeEventListener("load", renderGoogleButton);
        existingScript.removeEventListener("error", handleScriptError);
      };
    }

    const script = document.createElement("script");
    script.src = GOOGLE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.addEventListener("load", renderGoogleButton, { once: true });
    script.addEventListener("error", handleScriptError, { once: true });
    document.body.appendChild(script);

    return () => {
      script.removeEventListener("load", renderGoogleButton);
      script.removeEventListener("error", handleScriptError);
    };
  }, [copy.loginFailed, copy.originBlocked, copy.scriptError, googleClientId, isGoogleOriginAllowed, language]);

  async function handleGoogleCredential(credential: string) {
    setIsSubmitting(true);
    setError(null);
    try {
      await loginWithGoogle(credential);
      navigate(from, { replace: true });
    } catch (err) {
      setError(getFriendlyLoginError(err, copy.loginFailed));
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
      setError(getFriendlyLoginError(err, copy.demoFailed));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <Card className="auth-card">
        <span className="eyebrow">{copy.eyebrow}</span>
        <h1>{copy.title}</h1>
        <p>{copy.description}</p>
        <div className="google-button-wrap" ref={googleButtonRef}>
          {!googleClientId ? <span>{copy.missingClientId}</span> : null}
          {googleClientId && !isGoogleOriginAllowed ? <span>{copy.originBlocked}</span> : null}
        </div>
        <button type="button" className="primary-button full-width" onClick={handleDemoLogin} disabled={isSubmitting}>
          {copy.demoButton}
        </button>
        {error ? <p className="form-error">{error}</p> : null}
        <Link to="/" className="text-link">
          {copy.backHome}
        </Link>
      </Card>
    </main>
  );
}
