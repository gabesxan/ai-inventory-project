import React from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { AiDataPage } from "./pages/AiDataPage";
import { CatalogAuxPage } from "./pages/CatalogAuxPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { MovementsPage } from "./pages/MovementsPage";
import { ProductsPage } from "./pages/ProductsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { UsersPage } from "./pages/UsersPage";

function buildLoginRedirectUrl(
  pathname: string,
  search: string,
  expired: boolean
): string {
  const target = `${pathname}${search}`;
  const params = new URLSearchParams();
  if (expired) {
    params.set("expired", "1");
  }
  if (target && target !== "/" && !target.startsWith("/login")) {
    params.set("next", target);
  }
  const qs = params.toString();
  return qs ? `/login?${qs}` : "/login";
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading, sessionExpired } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="state-box" style={{ paddingTop: 80 }}>
        Verificando sessão...
      </div>
    );
  }
  if (!user) {
    return (
      <Navigate
        to={buildLoginRedirectUrl(location.pathname, location.search, sessionExpired)}
        replace
      />
    );
  }
  return <>{children}</>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, isAdmin, isLoading, sessionExpired } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <div className="state-box">Verificando permissões...</div>;
  }
  if (!user) {
    return (
      <Navigate
        to={buildLoginRedirectUrl(location.pathname, location.search, sessionExpired)}
        replace
      />
    );
  }
  if (!isAdmin) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/produtos" element={<ProductsPage />} />
            <Route path="/movimentacoes" element={<MovementsPage />} />
            <Route path="/cadastros-auxiliares" element={<CatalogAuxPage />} />
            <Route
              path="/relatorios"
              element={
                <AdminRoute>
                  <ReportsPage />
                </AdminRoute>
              }
            />
            <Route
              path="/sugestoes-compra"
              element={
                <AdminRoute>
                  <Navigate to="/relatorios?tab=replenishment" replace />
                </AdminRoute>
              }
            />
            <Route
              path="/dados-ia"
              element={
                <AdminRoute>
                  <AiDataPage />
                </AdminRoute>
              }
            />
            <Route
              path="/usuarios"
              element={
                <AdminRoute>
                  <UsersPage />
                </AdminRoute>
              }
            />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
