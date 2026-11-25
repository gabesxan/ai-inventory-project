import { useCallback, useEffect, useRef, useState } from "react";
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
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { translateRole } from "../utils/format";
import { BrandMark } from "./BrandMark";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  group: string;
  adminOnly?: boolean;
  end?: boolean;
}

// One list feeds the desktop capsule bar and the mobile drawer.
const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Painel", icon: BarChart3, group: "Visão Geral", end: true },
  { to: "/produtos", label: "Produtos", icon: Package, group: "Estoque" },
  { to: "/movimentacoes", label: "Movimentações", icon: ArrowLeftRight, group: "Estoque" },
  { to: "/cadastros-auxiliares", label: "Categorias e Fornecedores", icon: FolderTree, group: "Estoque" },
  { to: "/relatorios", label: "Relatórios", icon: FileSpreadsheet, group: "Relatórios", adminOnly: true },
  { to: "/dados-ia", label: "Importação e Dados", icon: Database, group: "Relatórios", adminOnly: true },
  { to: "/usuarios", label: "Usuários", icon: Users, group: "Administração", adminOnly: true },
];

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

  const items = NAV_ITEMS.filter((item) => isAdmin || !item.adminOnly);
  const groups = Array.from(new Set(items.map((item) => item.group)));

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
    if (!mobileOpen) return;
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
  }, [mobileOpen, closeMobile]);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const roleLabel = user ? translateRole(user.role) : "";

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Pular para o conteúdo principal
      </a>

      <header className="app-topbar">
        <div className="topbar-brand">
          <button
            ref={menuTriggerRef}
            type="button"
            className="btn btn-secondary btn-icon mobile-menu-btn"
            onClick={() => setMobileOpen(true)}
            aria-label="Abrir menu de navegação"
            aria-expanded={mobileOpen}
            aria-controls="primary-sidebar"
          >
            <Menu size={18} aria-hidden="true" />
          </button>
          <span className="brand-mark-wrap">
            <BrandMark size={30} />
          </span>
          <div className="brand-text">
            <span className="brand-name">EstoqueFácil</span>
            <span className="brand-subtitle">Depósito Único</span>
          </div>
        </div>

        <nav className="top-nav" aria-label="Navegação do sistema">
          {items.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `top-nav-link ${isActive ? "active" : ""}`}
            >
              <Icon size={16} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="topbar-account">
          <span className="user-avatar" title={user?.name} aria-hidden="true">
            {getInitials(user?.name)}
          </span>
          <span className="sr-only">
            {user?.name} · {roleLabel}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-icon topbar-logout"
            onClick={handleLogout}
            aria-label="Sair do sistema"
            title="Sair do sistema"
          >
            <LogOut size={16} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div
        className={`sidebar-backdrop ${mobileOpen ? "open" : ""}`}
        onClick={() => closeMobile(true)}
        aria-hidden="true"
      />

      {/* Drawer navigation for narrow screens; hidden on wide screens. */}
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

        <nav className="sidebar-nav" aria-label="Navegação do sistema (menu)">
          {groups.map((group) => (
            <div className="nav-group" key={group}>
              <div className="nav-section-label">{group}</div>
              {items
                .filter((item) => item.group === group)
                .map(({ to, label, icon: Icon, end }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={end}
                    onClick={() => closeMobile(false)}
                    className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                  >
                    <Icon size={17} aria-hidden="true" />
                    <span>{label}</span>
                  </NavLink>
                ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-account-row">
            <span className="user-avatar" aria-hidden="true">
              {getInitials(user?.name)}
            </span>
            <div className="user-pill">
              <strong>{user?.name}</strong>
              <span>{roleLabel}</span>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary sidebar-logout-btn"
            onClick={handleLogout}
          >
            <LogOut size={15} aria-hidden="true" />
            <span>Sair do sistema</span>
          </button>
        </div>
      </aside>

      <main id="main-content" className="app-sheet page-content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
