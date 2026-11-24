import React, { useCallback, useEffect, useState } from "react";
import { Ban, CheckCircle2, Info, Pencil, Plus, RotateCcw } from "lucide-react";
import { Modal } from "../components/Modal";
import { useAuth } from "../context/AuthContext";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type { Category, PaginatedResponse, Supplier } from "../types/api";

type CatalogTab = "categories" | "suppliers";

export function CatalogAuxPage() {
  const { isAdmin } = useAuth();
  const [tab, setTab] = useState<CatalogTab>("categories");

  const [categories, setCategories] = useState<Category[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);

  // Independent search state per tab so switching tabs never leaks filters or rows
  const [categorySearch, setCategorySearch] = useState("");
  const [supplierSearch, setSupplierSearch] = useState("");

  const [loadingCategories, setLoadingCategories] = useState(true);
  const [loadingSuppliers, setLoadingSuppliers] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Categoria modal
  const [catModalOpen, setCatModalOpen] = useState(false);
  const [editingCat, setEditingCat] = useState<Category | null>(null);
  const [catName, setCatName] = useState("");
  const [catDesc, setCatDesc] = useState("");
  const [catError, setCatError] = useState<string | null>(null);
  const [savingCat, setSavingCat] = useState(false);

  // Fornecedor modal
  const [supModalOpen, setSupModalOpen] = useState(false);
  const [editingSup, setEditingSup] = useState<Supplier | null>(null);
  const [supName, setSupName] = useState("");
  const [supDoc, setSupDoc] = useState("");
  const [supContact, setSupContact] = useState("");
  const [supEmail, setSupEmail] = useState("");
  const [supPhone, setSupPhone] = useState("");
  const [supLeadTime, setSupLeadTime] = useState("");
  const [supNotes, setSupNotes] = useState("");
  const [supError, setSupError] = useState<string | null>(null);
  const [savingSup, setSavingSup] = useState(false);

  const loadCategories = useCallback(async () => {
    setLoadingCategories(true);
    setError(null);
    try {
      const qs = buildQueryString({
        search: categorySearch.trim() || undefined,
        page_size: 200,
      });
      const res = await apiRequest<PaginatedResponse<Category>>(`/categories${qs}`);
      setCategories(res.items);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro ao carregar categorias."
      );
    } finally {
      setLoadingCategories(false);
    }
  }, [categorySearch]);

  const loadSuppliers = useCallback(async () => {
    setLoadingSuppliers(true);
    setError(null);
    try {
      const qs = buildQueryString({
        search: supplierSearch.trim() || undefined,
        page_size: 200,
      });
      const res = await apiRequest<PaginatedResponse<Supplier>>(`/suppliers${qs}`);
      setSuppliers(res.items);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro ao carregar fornecedores."
      );
    } finally {
      setLoadingSuppliers(false);
    }
  }, [supplierSearch]);

  useEffect(() => {
    loadCategories();
  }, [loadCategories]);

  useEffect(() => {
    loadSuppliers();
  }, [loadSuppliers]);

  const openCatModal = (cat?: Category) => {
    setEditingCat(cat || null);
    setCatName(cat?.name || "");
    setCatDesc(cat?.description || "");
    setCatError(null);
    setCatModalOpen(true);
  };

  const handleSaveCategory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (catName.trim().length < 2) {
      setCatError("Informe o nome da categoria (mínimo 2 caracteres).");
      return;
    }
    setSavingCat(true);
    setCatError(null);
    try {
      const payload = {
        name: catName.trim(),
        description: catDesc.trim() || null,
      };
      if (editingCat) {
        await apiRequest(`/categories/${editingCat.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setFeedback(`Categoria "${payload.name}" atualizada.`);
      } else {
        await apiRequest("/categories", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setFeedback(`Categoria "${payload.name}" cadastrada.`);
      }
      setCatModalOpen(false);
      await loadCategories();
    } catch (err) {
      setCatError(
        err instanceof ApiError ? err.message : "Erro ao salvar categoria."
      );
    } finally {
      setSavingCat(false);
    }
  };

  const handleToggleCategory = async (cat: Category) => {
    setError(null);
    try {
      await apiRequest(`/categories/${cat.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !cat.is_active }),
      });
      setFeedback(
        `Categoria "${cat.name}" ${!cat.is_active ? "ativada" : "inativada"}.`
      );
      await loadCategories();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erro ao atualizar status.");
    }
  };

  const openSupModal = (sup?: Supplier) => {
    setEditingSup(sup || null);
    setSupName(sup?.name || "");
    setSupDoc(sup?.document || "");
    setSupContact(sup?.contact_name || "");
    setSupEmail(sup?.email || "");
    setSupPhone(sup?.phone || "");
    setSupLeadTime(
      sup?.default_lead_time_days !== null && sup?.default_lead_time_days !== undefined
        ? String(sup.default_lead_time_days)
        : ""
    );
    setSupNotes(sup?.notes || "");
    setSupError(null);
    setSupModalOpen(true);
  };

  const handleSaveSupplier = async (e: React.FormEvent) => {
    e.preventDefault();
    if (supName.trim().length < 2) {
      setSupError("Informe o nome do fornecedor (mínimo 2 caracteres).");
      return;
    }
    if (supLeadTime.trim()) {
      const lt = Number(supLeadTime);
      if (!Number.isInteger(lt) || lt < 0) {
        setSupError("Informe um prazo padrão inteiro em dias (>= 0).");
        return;
      }
    }
    setSavingSup(true);
    setSupError(null);
    try {
      const payload = {
        name: supName.trim(),
        document: supDoc.trim() || null,
        contact_name: supContact.trim() || null,
        email: supEmail.trim() || null,
        phone: supPhone.trim() || null,
        default_lead_time_days: supLeadTime.trim() ? Number(supLeadTime) : null,
        notes: supNotes.trim() || null,
      };
      if (editingSup) {
        await apiRequest(`/suppliers/${editingSup.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setFeedback(`Fornecedor "${payload.name}" atualizado.`);
      } else {
        await apiRequest("/suppliers", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setFeedback(`Fornecedor "${payload.name}" cadastrado.`);
      }
      setSupModalOpen(false);
      await loadSuppliers();
    } catch (err) {
      setSupError(
        err instanceof ApiError ? err.message : "Erro ao salvar fornecedor."
      );
    } finally {
      setSavingSup(false);
    }
  };

  const handleToggleSupplier = async (sup: Supplier) => {
    setError(null);
    try {
      await apiRequest(`/suppliers/${sup.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !sup.is_active }),
      });
      setFeedback(
        `Fornecedor "${sup.name}" ${!sup.is_active ? "ativado" : "inativado"}.`
      );
      await loadSuppliers();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erro ao atualizar status.");
    }
  };

  const activeSearch = tab === "categories" ? categorySearch : supplierSearch;
  const setActiveSearch = (value: string) => {
    if (tab === "categories") setCategorySearch(value);
    else setSupplierSearch(value);
  };
  const isTabLoading = tab === "categories" ? loadingCategories : loadingSuppliers;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Categorias e Fornecedores</h1>
          <p className="page-subtitle">
            Organize o catálogo por categoria e mantenha fornecedores com identificação e prazo padrão de entrega.
          </p>
        </div>
        {isAdmin ? (
          <div className="header-actions">
            {tab === "categories" ? (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => openCatModal()}
              >
                <Plus size={16} aria-hidden="true" />
                <span>Nova Categoria</span>
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => openSupModal()}
              >
                <Plus size={16} aria-hidden="true" />
                <span>Novo Fornecedor</span>
              </button>
            )}
          </div>
        ) : null}
      </div>

      {!isAdmin ? (
        <div className="alert alert-info" role="status" data-testid="catalog-readonly-notice">
          <Info size={16} className="alert-icon" aria-hidden="true" />
          <div>
            Modo de consulta: apenas administradores podem criar, editar ou alterar o status de categorias e fornecedores.
          </div>
        </div>
      ) : null}

      {feedback ? (
        <div className="alert alert-success" role="status">
          {feedback}
        </div>
      ) : null}
      {error ? (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      ) : null}

      <div className="tabs-bar" role="tablist" aria-label="Cadastros auxiliares">
        <button
          type="button"
          role="tab"
          id="aux-tab-categories"
          aria-selected={tab === "categories"}
          aria-controls="aux-panel-categories"
          className={`tab-btn ${tab === "categories" ? "active" : ""}`}
          onClick={() => setTab("categories")}
        >
          Categorias ({categories.length})
        </button>
        <button
          type="button"
          role="tab"
          id="aux-tab-suppliers"
          aria-selected={tab === "suppliers"}
          aria-controls="aux-panel-suppliers"
          className={`tab-btn ${tab === "suppliers" ? "active" : ""}`}
          onClick={() => setTab("suppliers")}
        >
          Fornecedores ({suppliers.length})
        </button>
      </div>

      <section
        id={`aux-panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`aux-tab-${tab}`}
        className="card"
      >
        <div className="filters-bar">
          <div className="form-field" style={{ flex: "1 1 280px", maxWidth: 400 }}>
            <label htmlFor="aux-search">
              {tab === "categories"
                ? "Pesquisar categorias"
                : "Pesquisar fornecedores"}
            </label>
            <input
              id="aux-search"
              type="search"
              className="input"
              value={activeSearch}
              onChange={(e) => setActiveSearch(e.target.value)}
              placeholder={
                tab === "categories"
                  ? "Filtrar categoria por nome..."
                  : "Filtrar fornecedor por nome..."
              }
            />
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setActiveSearch("")}
            disabled={!activeSearch}
          >
            <RotateCcw size={14} aria-hidden="true" />
            <span>Limpar busca</span>
          </button>
        </div>

        {isTabLoading ? (
          <div className="state-box">Carregando registros...</div>
        ) : tab === "categories" ? (
          categories.length === 0 ? (
            <div className="state-box">
              {categorySearch.trim()
                ? "Nenhuma categoria encontrada para a busca informada."
                : "Nenhuma categoria cadastrada."}
            </div>
          ) : (
            <div
              className="table-wrap"
              role="region"
              aria-label="Tabela de categorias"
              tabIndex={0}
            >
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Descrição</th>
                    <th>Status</th>
                    {isAdmin ? <th>Ações</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {categories.map((cat) => (
                    <tr key={cat.id}>
                      <td>
                        <strong>{cat.name}</strong>
                      </td>
                      <td>{cat.description || "—"}</td>
                      <td>
                        <span
                          className={`badge ${
                            cat.is_active ? "badge-success" : "badge-neutral"
                          }`}
                        >
                          {cat.is_active ? "Ativa" : "Inativa"}
                        </span>
                      </td>
                      {isAdmin ? (
                        <td>
                          <div className="td-actions">
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => openCatModal(cat)}
                            >
                              <Pencil size={14} aria-hidden="true" />
                              <span>Editar</span>
                            </button>
                            <button
                              type="button"
                              className="btn btn-outline-danger btn-sm"
                              onClick={() => handleToggleCategory(cat)}
                            >
                              {cat.is_active ? (
                                <>
                                  <Ban size={14} aria-hidden="true" />
                                  <span>Inativar</span>
                                </>
                              ) : (
                                <>
                                  <CheckCircle2 size={14} aria-hidden="true" />
                                  <span>Reativar</span>
                                </>
                              )}
                            </button>
                          </div>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : suppliers.length === 0 ? (
          <div className="state-box">
            {supplierSearch.trim()
              ? "Nenhum fornecedor encontrado para a busca informada."
              : "Nenhum fornecedor cadastrado."}
          </div>
        ) : (
          <div
            className="table-wrap"
            role="region"
            aria-label="Tabela de fornecedores"
            tabIndex={0}
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>Fornecedor</th>
                  <th>CNPJ / CPF</th>
                  <th>Contato / Telefone / E-mail</th>
                  <th className="td-numeric">Prazo Padrão</th>
                  <th>Status</th>
                  {isAdmin ? <th>Ações</th> : null}
                </tr>
              </thead>
              <tbody>
                {suppliers.map((sup) => (
                  <tr key={sup.id}>
                    <td>
                      <strong>{sup.name}</strong>
                    </td>
                    <td className="mono">{sup.document || "—"}</td>
                    <td>
                      <div>{sup.contact_name || "—"}</div>
                      <div className="cell-subtext">
                        {[sup.phone, sup.email].filter(Boolean).join(" · ") || "—"}
                      </div>
                    </td>
                    <td className="td-numeric">
                      {sup.default_lead_time_days !== null
                        ? `${sup.default_lead_time_days} dias`
                        : "—"}
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          sup.is_active ? "badge-success" : "badge-neutral"
                        }`}
                      >
                        {sup.is_active ? "Ativo" : "Inativo"}
                      </span>
                    </td>
                    {isAdmin ? (
                      <td>
                        <div className="td-actions">
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => openSupModal(sup)}
                          >
                            <Pencil size={14} aria-hidden="true" />
                            <span>Editar</span>
                          </button>
                          <button
                            type="button"
                            className="btn btn-outline-danger btn-sm"
                            onClick={() => handleToggleSupplier(sup)}
                          >
                            {sup.is_active ? (
                              <>
                                <Ban size={14} aria-hidden="true" />
                                <span>Inativar</span>
                              </>
                            ) : (
                              <>
                                <CheckCircle2 size={14} aria-hidden="true" />
                                <span>Reativar</span>
                              </>
                            )}
                          </button>
                        </div>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <Modal
        isOpen={catModalOpen}
        onClose={() => setCatModalOpen(false)}
        title={editingCat ? "Editar Categoria" : "Nova Categoria"}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setCatModalOpen(false)}
            >
              Cancelar
            </button>
            <button
              type="submit"
              form="cat-form"
              className="btn btn-primary"
              disabled={savingCat}
            >
              <CheckCircle2 size={15} aria-hidden="true" />
              <span>{savingCat ? "Salvando..." : "Salvar Categoria"}</span>
            </button>
          </>
        }
      >
        {catError ? (
          <div className="alert alert-error" role="alert">
            {catError}
          </div>
        ) : null}
        <form id="cat-form" onSubmit={handleSaveCategory} className="form-grid">
          <div className="form-field full">
            <label htmlFor="cat-name">Nome *</label>
            <input
              id="cat-name"
              type="text"
              className={`input ${catError ? "has-error" : ""}`}
              value={catName}
              onChange={(e) => setCatName(e.target.value)}
            />
          </div>
          <div className="form-field full">
            <label htmlFor="cat-desc">Descrição (opcional)</label>
            <textarea
              id="cat-desc"
              className="textarea"
              value={catDesc}
              onChange={(e) => setCatDesc(e.target.value)}
            />
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={supModalOpen}
        onClose={() => setSupModalOpen(false)}
        title={editingSup ? "Editar Fornecedor" : "Novo Fornecedor"}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setSupModalOpen(false)}
            >
              Cancelar
            </button>
            <button
              type="submit"
              form="sup-form"
              className="btn btn-primary"
              disabled={savingSup}
            >
              <CheckCircle2 size={15} aria-hidden="true" />
              <span>{savingSup ? "Salvando..." : "Salvar Fornecedor"}</span>
            </button>
          </>
        }
      >
        {supError ? (
          <div className="alert alert-error" role="alert">
            {supError}
          </div>
        ) : null}
        <form id="sup-form" onSubmit={handleSaveSupplier} className="form-grid">
          <div className="form-field full">
            <label htmlFor="sup-name">Razão Social / Nome *</label>
            <input
              id="sup-name"
              type="text"
              className={`input ${supError ? "has-error" : ""}`}
              value={supName}
              onChange={(e) => setSupName(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="sup-doc">CNPJ / CPF (opcional)</label>
            <input
              id="sup-doc"
              type="text"
              className="input mono"
              value={supDoc}
              onChange={(e) => setSupDoc(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="sup-lt">Prazo Padrão de Entrega (dias)</label>
            <input
              id="sup-lt"
              type="number"
              min="0"
              className="input"
              value={supLeadTime}
              onChange={(e) => setSupLeadTime(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="sup-contact">Pessoa de Contato</label>
            <input
              id="sup-contact"
              type="text"
              className="input"
              value={supContact}
              onChange={(e) => setSupContact(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor="sup-phone">Telefone</label>
            <input
              id="sup-phone"
              type="text"
              className="input"
              value={supPhone}
              onChange={(e) => setSupPhone(e.target.value)}
            />
          </div>
          <div className="form-field full">
            <label htmlFor="sup-email">E-mail</label>
            <input
              id="sup-email"
              type="email"
              className="input"
              value={supEmail}
              onChange={(e) => setSupEmail(e.target.value)}
            />
          </div>
          <div className="form-field full">
            <label htmlFor="sup-notes">Observações</label>
            <textarea
              id="sup-notes"
              className="textarea"
              value={supNotes}
              onChange={(e) => setSupNotes(e.target.value)}
            />
          </div>
        </form>
      </Modal>
    </div>
  );
}
