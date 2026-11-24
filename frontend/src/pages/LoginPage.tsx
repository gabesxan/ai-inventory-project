import React, { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";
import { BrandMark } from "../components/BrandMark";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../services/api";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!email.trim() || !email.includes("@")) {
      errors.email = "Informe um e-mail válido.";
    }
    if (!password) {
      errors.password = "Informe sua senha.";
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    setErrorMessage(null);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Falha ao conectar ao servidor. Tente novamente.");
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
            <p>Acesse o sistema de gestão de estoque</p>
          </div>
        </div>

        {errorMessage ? (
          <div className="alert alert-error" role="alert">
            {errorMessage}
          </div>
        ) : null}

        <form onSubmit={handleSubmit} noValidate>
          <div className="form-field" style={{ marginBottom: 14 }}>
            <label htmlFor="login-email">E-mail</label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              className={`input ${fieldErrors.email ? "has-error" : ""}`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@empresa.local"
            />
            {fieldErrors.email ? (
              <span className="field-error">{fieldErrors.email}</span>
            ) : null}
          </div>

          <div className="form-field" style={{ marginBottom: 20 }}>
            <label htmlFor="login-password">Senha</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              className={`input ${fieldErrors.password ? "has-error" : ""}`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Digite sua senha"
            />
            {fieldErrors.password ? (
              <span className="field-error">{fieldErrors.password}</span>
            ) : null}
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%" }}
            disabled={submitting}
          >
            <LogIn size={18} />
            <span>{submitting ? "Entrando..." : "Entrar no sistema"}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
