import React, { useMemo, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, Clock, Eye, EyeOff, LogIn } from "lucide-react";
import { BrandMark } from "../components/BrandMark";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../services/api";

/**
 * Only allows relative internal application routes to prevent open redirects.
 */
function sanitizeInternalDestination(raw: string | null): string {
  if (!raw) return "/";
  const trimmed = raw.trim();
  if (
    !trimmed.startsWith("/") ||
    trimmed.startsWith("//") ||
    trimmed.startsWith("/login") ||
    /^\/[a-zA-Z]+:/.test(trimmed)
  ) {
    return "/";
  }
  return trimmed;
}

export function LoginPage() {
  const { user, login, sessionExpired, clearSessionExpired } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const safeDestination = useMemo(
    () => sanitizeInternalDestination(searchParams.get("next")),
    [searchParams]
  );
  const showExpiredNotice =
    sessionExpired || searchParams.get("expired") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    return <Navigate to={safeDestination} replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!email.trim() || !email.includes("@")) {
      errors.email = "Informe um endereço de e-mail válido.";
    }
    if (!password) {
      errors.password = "Informe sua senha para continuar.";
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    setErrorMessage(null);
    clearSessionExpired();
    try {
      await login(email.trim(), password);
      navigate(safeDestination, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setErrorMessage(
            "E-mail ou senha inválidos. Verifique seus dados e tente novamente."
          );
        } else if (err.status === 403) {
          setErrorMessage(
            "Sua conta está inativa ou sem permissão de acesso. Procure o administrador."
          );
        } else {
          setErrorMessage(err.message);
        }
      } else {
        setErrorMessage(
          "Não foi possível conectar ao servidor. Verifique a conexão e tente novamente."
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="login-brand-icon">
            <BrandMark size={28} />
          </div>
          <div>
            <h1>EstoqueFácil</h1>
            <p>Gestão de estoque · Depósito Único</p>
          </div>
        </div>

        {showExpiredNotice ? (
          <div
            className="alert alert-warning"
            role="status"
            data-testid="session-expired-notice"
          >
            <Clock size={17} className="alert-icon" aria-hidden="true" />
            <div>
              <strong>Sua sessão expirou.</strong> Entre novamente para retomar o acesso
              {safeDestination !== "/" ? " à tela anterior." : "."}
            </div>
          </div>
        ) : null}

        {errorMessage ? (
          <div className="alert alert-error" role="alert" data-testid="login-error-alert">
            <AlertCircle size={17} className="alert-icon" aria-hidden="true" />
            <div>{errorMessage}</div>
          </div>
        ) : null}

        <form onSubmit={handleSubmit} noValidate>
          <div className="form-field" style={{ marginBottom: 14 }}>
            <label htmlFor="login-email">E-mail</label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              className={`input ${fieldErrors.email ? "has-error" : ""}`}
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? "login-email-error" : undefined}
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (fieldErrors.email) {
                  setFieldErrors((prev) => ({ ...prev, email: "" }));
                }
              }}
              placeholder="nome@empresa.local"
            />
            {fieldErrors.email ? (
              <span id="login-email-error" className="field-error" role="alert">
                {fieldErrors.email}
              </span>
            ) : null}
          </div>

          <div className="form-field" style={{ marginBottom: 20 }}>
            <label htmlFor="login-password">Senha</label>
            <div className="password-input-wrap">
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                className={`input ${fieldErrors.password ? "has-error" : ""}`}
                aria-invalid={Boolean(fieldErrors.password)}
                aria-describedby={
                  fieldErrors.password ? "login-password-error" : undefined
                }
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (fieldErrors.password) {
                    setFieldErrors((prev) => ({ ...prev, password: "" }));
                  }
                }}
                placeholder="Digite sua senha"
              />
              <button
                type="button"
                className="btn btn-subtle btn-icon password-toggle-btn"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                aria-pressed={showPassword}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            {fieldErrors.password ? (
              <span id="login-password-error" className="field-error" role="alert">
                {fieldErrors.password}
              </span>
            ) : null}
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%" }}
            disabled={submitting}
          >
            <LogIn size={16} aria-hidden="true" />
            <span>{submitting ? "Entrando..." : "Entrar no sistema"}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
