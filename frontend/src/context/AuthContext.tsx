import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  apiRequest,
  getStoredToken,
  registerUnauthorizedHandler,
  setStoredToken,
} from "../services/api";
import type { TokenResponse, User } from "../types/api";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAdmin: boolean;
  sessionExpired: boolean;
  clearSessionExpired: () => void;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [sessionExpired, setSessionExpired] = useState<boolean>(false);

  const clearSession = useCallback((expired = false) => {
    setStoredToken(null);
    setUser(null);
    setSessionExpired(expired);
  }, []);

  const clearSessionExpired = useCallback(() => {
    setSessionExpired(false);
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(() => clearSession(true));
  }, [clearSession]);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    apiRequest<User>("/auth/me")
      .then((me) => {
        setUser(me);
        setSessionExpired(false);
      })
      .catch(() => clearSession(true))
      .finally(() => setIsLoading(false));
  }, [clearSession]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiRequest<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setStoredToken(res.access_token);
    setUser(res.user);
    setSessionExpired(false);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiRequest("/auth/logout", { method: "POST" });
    } catch {
      // mesmo se o token já tiver expirado, limpa a sessão local
    } finally {
      clearSession(false);
    }
  }, [clearSession]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAdmin: user?.role === "ADMIN",
        sessionExpired,
        clearSessionExpired,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth deve ser utilizado dentro de AuthProvider.");
  }
  return ctx;
}
