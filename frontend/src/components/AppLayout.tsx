import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeftRight,
  BarChart3,
  Database,
  FileSpreadsheet,
  FolderTree,
  LogOut,
  Menu,
  Package,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { translateRole } from "../utils/format";
import { BrandMark } from "./BrandMark";

interface RouteMeta {
  group: string;
  title: string;
}

const ROUTE_META: Record<string, RouteMeta> = {
  "/": { group: "Visão Geral", title: "Painel de Estoque" },
  "/produtos": { group: "Estoque", title: "Produtos e Saldos" },
  "/movimentacoes": { group: "Estoque", title: "Movimentações" },
  "/cadastros-auxiliares": { group: "Estoque", title: "Categorias e Fornecedores" },
  "/relatorios": { group: "Relatórios", title: "Relatórios Gerenciais" },
  "/sugestoes-compra": { group: "Relatórios", title: "Reposição" },
  "/dados-ia": { group: "Relatórios", title: "Importação e Dados" },
  "/usuarios": { group: "Administração", title: "Usuários e Permissões" },
};

function getInitials(name?: string): string {
  if (!name) return "EF";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "EF";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function AppLayout() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const menuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);
  const wasMobileOpenRef = useRef(false);

  const currentMeta = useMemo<RouteMeta>(() => {
    return ROUTE_META[location.pathname] ?? { group: "EstoqueFácil", title: "Operação" };
  }, [location.pathname]);

  const closeMobile = useCallback((restoreFocus = false) => {
    setMobileOpen(false);
    if (restoreFocus) {
      window.requestAnimationFrame(() => {
        menuTriggerRef.current?.focus();
      });
    }
  }, []);

  // Close mobile drawer when navigating via browser history
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname, location.search]);

  // Manage keyboard focus and Escape key for mobile drawer
  useEffect(() => {
    if (mobileOpen) {
      wasMobileOpenRef.current = true;
      const frame = window.requestAnimationFrame(() => {
        closeButtonRef.current?.focus();
      });
      const onKeyDown = (event: KeyboardEvent) => {
        if (event.key === "Escape") {
          event.preventDefault();
          closeMobile(true);
          return;
        }
        if (event.key === "Tab" && sidebarRef.current) {
          const focusables = Array.from(
            sidebarRef.current.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
          ).filter((el) => el.offsetParent !== null);
          if (focusables.length === 0) return;
          const first = focusables[0];
          const last = focusables[focusables.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }
      };
      window.addEventListener("keydown", onKeyDown);
      return () => {
        window.cancelAnimationFrame(frame);
        window.removeEventListener("keydown", onKeyDown);
      };
    } else if (wasMobileOpenRef.current) {
      wasMobileOpenRef.current = false;
    }
  }, [mobileOpen, closeMobile]);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Pular para o conteúdo principal
      </a>

      <div
        className={`sidebar-backdrop ${mobileOpen ? "open" : ""}`}
        onClick={() => closeMobile(true)}
        aria-hidden="true"
      />

      <aside
        id="primary-sidebar"
        ref={sidebarRef}
        className={`sidebar ${mobileOpen ? "open" : ""}`}
        aria-label="Menu principal"
      >
        <div className="sidebar-brand">
          <div className="brand-title">
            <span className="brand-mark-wrap">
              <BrandMark size={26} />
            </span>
            <div className="brand-text">
              <span className="brand-name">EstoqueFácil</span>
              <span className="brand-subtitle">Depósito Único</span>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="btn btn-subtle btn-icon sidebar-close-btn"
            onClick={() => closeMobile(true)}
            aria-label="Fechar menu de navegação"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Navegação do sistema">
          <div className="nav-group">
            <div className="nav-section-label">Visão Geral</div>
            <NavLink
              to="/"
              end
              onClick={() => closeMobile(false)}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <BarChart3 size={17} aria-hidden="true" />
              <span>Painel</span>
            </NavLink>
          </div>

          <div className="nav-group">
            <div className="nav-section-label">Estoque</div>
            <NavLink
              to="/produtos"
              onClick={() => closeMobile(false)}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <Package size={17} aria-hidden="true" />
              <span>Produtos</span>
            </NavLink>
            <NavLink
              to="/movimentacoes"
              onClick={() => closeMobile(false)}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <ArrowLeftRight size={17} aria-hidden="true" />
              <span>Movimentações</span>
            </NavLink>
            <NavLink
              to="/cadastros-auxiliares"
              onClick={() => closeMobile(false)}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            >
              <FolderTree size={17} aria-hidden="true" />
              <span>Categorias e Fornecedores</span>
            </NavLink>
          </div>

          {isAdmin ? (
            <>
              <div className="nav-group">
                <div className="nav-section-label">Relatórios</div>
                <NavLink
                  to="/relatorios"
                  onClick={() => closeMobile(false)}
                  className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                >
                  <FileSpreadsheet size={17} aria-hidden="true" />
                  <span>Relatórios</span>
                </NavLink>
                <NavLink
                  to="/dados-ia"
                  onClick={() => closeMobile(false)}
                  className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                >
                  <Database size={17} aria-hidden="true" />
                  <span>Importação e Dados</span>
                </NavLink>
              </div>

              <div className="nav-group">
                <div className="nav-section-label">Administração</div>
                <NavLink
                  to="/usuarios"
                  onClick={() => closeMobile(false)}
                  className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                >
                  <Users size={17} aria-hidden="true" />
                  <span>Usuários</span>
                </NavLink>
              </div>
            </>
          ) : null}
        </nav>

        <div className="sidebar-footer">
          <div className="user-account-row">
            <span className="user-avatar" aria-hidden="true">
              {getInitials(user?.name)}
            </span>
            <div className="user-pill">
              <strong>{user?.name}</strong>
              <span>{user ? translateRole(user.role) : ""}</span>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm sidebar-logout-btn"
            onClick={handleLogout}
          >
            <LogOut size={15} aria-hidden="true" />
            <span>Sair do sistema</span>
          </button>
        </div>
      </aside>

      <div className="main-area">
        <header className="app-topbar">
          <div className="topbar-left">
            <button
              ref={menuTriggerRef}
              type="button"
              className="btn btn-secondary btn-sm mobile-menu-btn"
              onClick={() => setMobileOpen(true)}
              aria-label="Abrir menu de navegação"
              aria-expanded={mobileOpen}
              aria-controls="primary-sidebar"
            >
              <Menu size={17} aria-hidden="true" />
              <span>Menu</span>
            </button>
            <div className="topbar-breadcrumb" aria-label="Localização atual">
              <span className="topbar-group">{currentMeta.group}</span>
              <span className="topbar-sep" aria-hidden="true">
                /
              </span>
              <span className="topbar-section">{currentMeta.title}</span>
            </div>
          </div>

          <div className="topbar-right">
            <span className="topbar-context-pill">Depósito Único</span>
            {user ? (
              <span className="badge badge-neutral">
                {translateRole(user.role)}
              </span>
            ) : null}
          </div>
        </header>

        <main id="main-content" className="page-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
