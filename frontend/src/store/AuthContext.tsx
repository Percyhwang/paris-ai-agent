import { createContext, useContext, useEffect, useState } from "react";
import { authService } from "../services/authService";
import { getStoredTokens } from "../services/apiClient";
import { userService } from "../services/userService";
import type { User, UserPreferences } from "../types";

type AuthContextValue = {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  loginWithGoogle: (credential: string) => Promise<void>;
  demoLogin: () => Promise<void>;
  updatePreferences: (preferences: Partial<UserPreferences>) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function bootstrap() {
      if (!getStoredTokens()) {
        setIsLoading(false);
        return;
      }
      try {
        const me = await authService.me();
        if (mounted) setUser(me);
      } catch {
        authService.logout();
      } finally {
        if (mounted) setIsLoading(false);
      }
    }
    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  async function loginWithGoogle(credential: string) {
    const response = await authService.loginWithGoogleCredential(credential);
    setUser(response.user);
  }

  async function demoLogin() {
    const response = await authService.demoLogin();
    setUser(response.user);
  }

  async function updatePreferences(preferences: Partial<UserPreferences>) {
    if (!user) return;
    const updatedUser = await userService.updateMe({
      preferences: {
        ...user.preferences,
        ...preferences,
      },
    });
    setUser(updatedUser);
  }

  function logout() {
    authService.logout();
    setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: Boolean(user),
        isLoading,
        loginWithGoogle,
        demoLogin,
        updatePreferences,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
