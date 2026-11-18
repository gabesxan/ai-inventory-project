import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  ArrowLeftRight,
  BarChart3,
  Boxes,
  Database,
  FileSpreadsheet,
  FolderTree,
  LogOut,
  Menu,
  Package,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { translateRole } from "../utils/format";

export function AppLayout() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const closeMobile = () => setMobileOpen(false);

  return (
    <div className="app-shell">
      <div
        className={`sidebar-backdrop ${mobileOpen ? "open" : ""}`}
        onClick={closeMobile}
        aria-hidden="true"
      />

      <aside
        className={`sidebar ${mobileOpen ? "open" : ""}`}
        aria-label="Menu principal"
      >
        <div className="sidebar-brand">
          <div className="brand-title">
            <Boxes size={24} color="#60a5fa" />
            <div>
              EstoqueFácil IA
              <span className="brand-subtitle">Depósito Único · v1.0</span>
            </div>
          </div>
          {mobileOpen ? (
            <button
              type="button"
              className="btn btn-ghost-dark btn-sm"
              onClick={closeMobile}
              aria-label="Fechar menu"
            >
              <X size={16} />
            </button>
          ) : null}
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">Operação Diária</div>
          <NavLink
            to="/"
            end
            onClick={closeMobile}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <BarChart3 size={18} />
            <span>Painel</span>
          </NavLink>
          <NavLink
            to="/produtos"
            onClick={closeMobile}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Package size={18} />
            <span>Produtos</span>
          </NavLink>
          <NavLink
            to="/movimentacoes"
            onClick={closeMobile}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <ArrowLeftRight size={18} />
            <span>Movimentações</span>
          </NavLink>
          <NavLink
            to="/cadastros-auxiliares"
            onClick={closeMobile}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <FolderTree size={18} />
            <span>Categorias e Fornecedores</span>
          </NavLink>

          {isAdmin ? (
            <>
              <div className="nav-section-label">Gestão e Inteligência</div>
              <NavLink
                to="/relatorios"
                onClick={closeMobile}
                className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              >
                <FileSpreadsheet size={18} />
                <span>Relatórios</span>
              </NavLink>
              <NavLink
                to="/sugestoes-compra"
                onClick={closeMobile}
                className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              >
                <Sparkles size={18} />
                <span>Sugestões de Compra</span>
              </NavLink>
              <NavLink
                to="/dados-ia"
                onClick={closeMobile}
                className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              >
                <Database size={18} />
                <span>Dados para IA</span>
              </NavLink>
              <NavLink
                to="/usuarios"
                onClick={closeMobile}
                className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              >
                <Users size={18} />
                <span>Usuários</span>
              </NavLink>
            </>
          ) : null}
        </nav>

        <div className="sidebar-footer">
          <div className="user-pill">
            <strong>{user?.name}</strong>
            <span>{user ? translateRole(user.role) : ""}</span>
          </div>
          <button
            type="button"
            className="btn btn-ghost-dark"
            onClick={handleLogout}
          >
            <LogOut size={16} />
            <span>Sair do sistema</span>
          </button>
        </div>
      </aside>

      <div className="main-area">
        <header className="mobile-topbar">
          <div className="brand-title">
            <Boxes size={20} color="#60a5fa" />
            <span>EstoqueFácil IA</span>
          </div>
          <button
            type="button"
            className="mobile-menu-btn"
            onClick={() => setMobileOpen(true)}
            aria-label="Abrir menu de navegação"
          >
            <Menu size={18} />
            <span>Menu</span>
          </button>
        </header>

        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
