import React, { useCallback, useEffect, useState } from "react";
import { Ban, CheckCircle2, Pencil, Plus } from "lucide-react";
import { Modal } from "../components/Modal";
import { Pagination } from "../components/Pagination";
import { useAuth } from "../context/AuthContext";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type { PaginatedResponse, User, UserRole } from "../types/api";
import { formatDateTimeBR, translateRole } from "../utils/format";

export function UsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("OPERATOR");
  const [password, setPassword] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({
        search: search.trim() || undefined,
        page,
        page_size: 20,
      });
      const res = await apiRequest<PaginatedResponse<User>>(`/users${qs}`);
      setUsers(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro ao carregar usuários."
      );
    } finally {
      setLoading(false);
    }
  }, [search, page]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const openCreate = () => {
    setEditing(null);
    setName("");
    setEmail("");
    setRole("OPERATOR");
    setPassword("");
    setFormErrors({});
    setSubmitError(null);
    setModalOpen(true);
  };

  const openEdit = (u: User) => {
    setEditing(u);
    setName(u.name);
    setEmail(u.email);
    setRole(u.role);
    setPassword("");
    setFormErrors({});
    setSubmitError(null);
    setModalOpen(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (name.trim().length < 2) errs.name = "Informe o nome completo.";
    if (!email.trim() || !email.includes("@")) errs.email = "Informe um e-mail válido.";
    if (!editing && password.length < 6) {
      errs.password = "A senha deve ter no mínimo 6 caracteres.";
    } else if (editing && password.length > 0 && password.length < 6) {
      errs.password = "A nova senha deve ter no mínimo 6 caracteres.";
    }
    setFormErrors(errs);
    if (Object.keys(errs).length > 0) return;

    setSaving(true);
    setSubmitError(null);
    try {
      if (editing) {
        await apiRequest(`/users/${editing.id}`, {
          method: "PUT",
          body: JSON.stringify({
            name: name.trim(),
            email: email.trim(),
            role,
            password: password || null,
          }),
        });
        setFeedback(`Usuário "${name.trim()}" atualizado com sucesso.`);
      } else {
        await apiRequest("/users", {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            email: email.trim(),
            role,
            password,
          }),
        });
        setFeedback(`Usuário "${name.trim()}" cadastrado com sucesso.`);
      }
      setModalOpen(false);
      await loadUsers();
    } catch (err) {
      setSubmitError(
        err instanceof ApiError ? err.message : "Erro ao salvar usuário."
      );
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStatus = async (u: User) => {
    setError(null);
    try {
      await apiRequest(`/users/${u.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !u.is_active }),
      });
      setFeedback(
        `Usuário "${u.name}" ${!u.is_active ? "reativado" : "inativado"}.`
      );
      await loadUsers();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro ao atualizar status."
      );
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Usuários e Permissões</h1>
          <p className="page-subtitle">
            Gerencie contas de Administradores e Operadores com controle de acesso validado no servidor.
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            <Plus size={16} />
            <span>Novo Usuário</span>
          </button>
        </div>
      </div>

      {feedback ? <div className="alert alert-success">{feedback}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      <div className="card">
        <div className="filters-bar">
          <div className="form-field" style={{ maxWidth: 360, width: "100%" }}>
            <label htmlFor="usr-search">Pesquisar (nome ou e-mail)</label>
            <input
              id="usr-search"
              type="search"
              className="input"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Filtrar usuários..."
            />
          </div>
        </div>

        {loading ? (
          <div className="state-box">Carregando usuários...</div>
        ) : users.length === 0 ? (
          <div className="state-box">Nenhum usuário encontrado.</div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>E-mail</th>
                    <th>Perfil</th>
                    <th>Status</th>
                    <th>Criado em</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.name}</strong>
                        {currentUser?.id === u.id ? (
                          <span className="badge badge-info" style={{ marginLeft: 8 }}>
                            Você
                          </span>
                        ) : null}
                      </td>
                      <td>{u.email}</td>
                      <td>
                        <span
                          className={`badge ${
                            u.role === "ADMIN" ? "badge-info" : "badge-neutral"
                          }`}
                        >
                          {translateRole(u.role)}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            u.is_active ? "badge-success" : "badge-neutral"
                          }`}
                        >
                          {u.is_active ? "Ativo" : "Inativo"}
                        </span>
                      </td>
                      <td>{formatDateTimeBR(u.created_at)}</td>
                      <td>
                        <div className="td-actions">
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => openEdit(u)}
                          >
                            <Pencil size={14} />
                            <span>Editar</span>
                          </button>
                          {currentUser?.id !== u.id ? (
                            <button
                              type="button"
                              className="btn btn-outline-danger btn-sm"
                              onClick={() => handleToggleStatus(u)}
                            >
                              {u.is_active ? (
                                <>
                                  <Ban size={14} />
                                  <span>Inativar</span>
                                </>
                              ) : (
                                <>
                                  <CheckCircle2 size={14} />
                                  <span>Reativar</span>
                                </>
                              )}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={page}
              totalPages={totalPages}
              totalItems={total}
              onPageChange={setPage}
            />
          </>
        )}
      </div>

      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? `Editar Usuário: ${editing.name}` : "Novo Usuário"}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setModalOpen(false)}
            >
              Cancelar
            </button>
            <button
              type="submit"
              form="user-form"
              className="btn btn-primary"
              disabled={saving}
            >
              <CheckCircle2 size={16} />
              <span>{saving ? "Salvando..." : "Salvar Usuário"}</span>
            </button>
          </>
        }
      >
        {submitError ? <div className="alert alert-error">{submitError}</div> : null}
        <form id="user-form" onSubmit={handleSave} className="form-grid">
          <div className="form-field full">
            <label htmlFor="uf-name">Nome completo *</label>
            <input
              id="uf-name"
              type="text"
              className={`input ${formErrors.name ? "has-error" : ""}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            {formErrors.name ? (
              <span className="field-error">{formErrors.name}</span>
            ) : null}
          </div>

          <div className="form-field full">
            <label htmlFor="uf-email">E-mail *</label>
            <input
              id="uf-email"
              type="email"
              className={`input ${formErrors.email ? "has-error" : ""}`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            {formErrors.email ? (
              <span className="field-error">{formErrors.email}</span>
            ) : null}
          </div>

          <div className="form-field">
            <label htmlFor="uf-role">Perfil *</label>
            <select
              id="uf-role"
              className="select"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
            >
              <option value="OPERATOR">Operador (consulta e entrada/saída)</option>
              <option value="ADMIN">Administrador (acesso completo)</option>
            </select>
          </div>

          <div className="form-field">
            <label htmlFor="uf-pass">
              {editing ? "Nova Senha (opcional)" : "Senha inicial *"}
            </label>
            <input
              id="uf-pass"
              type="password"
              className={`input ${formErrors.password ? "has-error" : ""}`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={editing ? "Manter senha atual" : "Mínimo 6 caracteres"}
            />
            {formErrors.password ? (
              <span className="field-error">{formErrors.password}</span>
            ) : null}
          </div>
        </form>
      </Modal>
    </div>
  );
}
