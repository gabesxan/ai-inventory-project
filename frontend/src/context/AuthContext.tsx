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
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const clearSession = useCallback(() => {
    setStoredToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(clearSession);
  }, [clearSession]);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    apiRequest<User>("/auth/me")
      .then((me) => setUser(me))
      .catch(() => clearSession())
      .finally(() => setIsLoading(false));
  }, [clearSession]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiRequest<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setStoredToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiRequest("/auth/logout", { method: "POST" });
    } catch {
      // mesmo se o token já tiver expirado, limpa a sessão local
    } finally {
      clearSession();
    }
  }, [clearSession]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAdmin: user?.role === "ADMIN",
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
