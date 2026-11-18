import React, { useCallback, useEffect, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Ban,
  CheckCircle2,
  Pencil,
  Plus,
  Search,
} from "lucide-react";
import { ConfirmModal } from "../components/ConfirmModal";
import { Modal } from "../components/Modal";
import { MovementModal, type MovementModalMode } from "../components/MovementModal";
import { Pagination } from "../components/Pagination";
import { useAuth } from "../context/AuthContext";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type {
  Category,
  PaginatedResponse,
  Product,
  Supplier,
  UnitSpec,
} from "../types/api";
import {
  formatCurrencyBRL,
  formatDateTimeBR,
  formatQuantity,
  isDiscreteUnitCode,
  translateStockStatus,
} from "../utils/format";

interface ProductFormState {
  name: string;
  sku: string;
  barcode: string;
  description: string;
  category_id: string;
  unit: string;
  unit_cost: string;
  min_stock: string;
  safety_stock: string;
  location: string;
  preferred_supplier_id: string;
  lead_time_days: string;
}

const EMPTY_FORM: ProductFormState = {
  name: "",
  sku: "",
  barcode: "",
  description: "",
  category_id: "",
  unit: "UN",
  unit_cost: "0.00",
  min_stock: "0",
  safety_stock: "0",
  location: "",
  preferred_supplier_id: "",
  lead_time_days: "",
};

export function ProductsPage() {
  const { isAdmin } = useAuth();

  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("true");
  const [stockFilter, setStockFilter] = useState("");

  const [categories, setCategories] = useState<Category[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [units, setUnits] = useState<UnitSpec[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Modal de criação/edição de produto
  const [formOpen, setFormOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [formState, setFormState] = useState<ProductFormState>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [formSubmitError, setFormSubmitError] = useState<string | null>(null);
  const [savingProduct, setSavingProduct] = useState(false);

  // Modal de ativação/inativação
  const [toggleTarget, setToggleTarget] = useState<Product | null>(null);
  const [toggling, setToggling] = useState(false);

  // Modal rápido de Entrada / Saída
  const [mvOpen, setMvOpen] = useState(false);
  const [mvMode, setMvMode] = useState<MovementModalMode>("ENTRADA");
  const [mvProductId, setMvProductId] = useState<number | null>(null);

  const loadAuxData = useCallback(async () => {
    try {
      const [catRes, supRes, unitRes] = await Promise.all([
        apiRequest<PaginatedResponse<Category>>("/categories?page_size=200"),
        apiRequest<PaginatedResponse<Supplier>>("/suppliers?page_size=200"),
        apiRequest<UnitSpec[]>("/products/units"),
      ]);
      setCategories(catRes.items);
      setSuppliers(supRes.items);
      setUnits(unitRes);
    } catch {
      // tratado pela listagem principal se necessário
    }
  }, []);

  const loadProducts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({
        search: search.trim() || undefined,
        category_id: categoryFilter || undefined,
        is_active: statusFilter === "" ? undefined : statusFilter,
        stock_status: stockFilter || undefined,
        page,
        page_size: 15,
      });
      const res = await apiRequest<PaginatedResponse<Product>>(`/products${qs}`);
      setProducts(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro ao carregar produtos."
      );
    } finally {
      setLoading(false);
    }
  }, [search, categoryFilter, statusFilter, stockFilter, page]);

  useEffect(() => {
    loadAuxData();
  }, [loadAuxData]);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  const openCreateModal = () => {
    const activeCats = categories.filter((c) => c.is_active);
    setEditingProduct(null);
    setFormState({
      ...EMPTY_FORM,
      category_id: activeCats[0] ? String(activeCats[0].id) : "",
    });
    setFormErrors({});
    setFormSubmitError(null);
    setFormOpen(true);
  };

  const openEditModal = (prod: Product) => {
    setEditingProduct(prod);
    setFormState({
      name: prod.name,
      sku: prod.sku,
      barcode: prod.barcode || "",
      description: prod.description || "",
      category_id: String(prod.category_id),
      unit: prod.unit,
      unit_cost: String(prod.unit_cost),
      min_stock: String(prod.min_stock),
      safety_stock: String(prod.safety_stock),
      location: prod.location || "",
      preferred_supplier_id: prod.preferred_supplier_id
        ? String(prod.preferred_supplier_id)
        : "",
      lead_time_days:
        prod.lead_time_days !== null ? String(prod.lead_time_days) : "",
    });
    setFormErrors({});
    setFormSubmitError(null);
    setFormOpen(true);
  };

  const validateProductForm = (): boolean => {
    const errs: Record<string, string> = {};
    if (formState.name.trim().length < 2) {
      errs.name = "Informe o nome do produto (mínimo 2 caracteres).";
    }
    const cleanSku = formState.sku.trim();
    if (cleanSku.length < 2 || cleanSku.includes(" ")) {
      errs.sku = "Informe um SKU válido sem espaços (mínimo 2 caracteres).";
    }
    if (!formState.category_id) {
      errs.category_id = "Selecione uma categoria.";
    }
    const cost = Number(formState.unit_cost.replace(",", "."));
    if (Number.isNaN(cost) || cost < 0) {
      errs.unit_cost = "Informe um custo unitário válido (>= 0).";
    }
    const minStock = Number(formState.min_stock.replace(",", "."));
    if (Number.isNaN(minStock) || minStock < 0) {
      errs.min_stock = "Informe um estoque mínimo válido (>= 0).";
    } else if (isDiscreteUnitCode(formState.unit) && !Number.isInteger(minStock)) {
      errs.min_stock = `A unidade ${formState.unit} exige valor inteiro.`;
    }
    const safety = Number(formState.safety_stock.replace(",", "."));
    if (Number.isNaN(safety) || safety < 0) {
      errs.safety_stock = "Informe um estoque de segurança válido (>= 0).";
    } else if (isDiscreteUnitCode(formState.unit) && !Number.isInteger(safety)) {
      errs.safety_stock = `A unidade ${formState.unit} exige valor inteiro.`;
    }
    if (formState.lead_time_days.trim()) {
      const lt = Number(formState.lead_time_days);
      if (!Number.isInteger(lt) || lt < 0) {
        errs.lead_time_days = "Informe um prazo inteiro em dias (>= 0).";
      }
    }
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSaveProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateProductForm()) return;

    setSavingProduct(true);
    setFormSubmitError(null);

    const payload = {
      name: formState.name.trim(),
      sku: formState.sku.trim().toUpperCase(),
      barcode: formState.barcode.trim() || null,
      description: formState.description.trim() || null,
      category_id: Number(formState.category_id),
      unit: formState.unit,
      unit_cost: formState.unit_cost.replace(",", ".").trim() || "0.00",
      min_stock: formState.min_stock.replace(",", ".").trim() || "0",
      safety_stock: formState.safety_stock.replace(",", ".").trim() || "0",
      location: formState.location.trim() || null,
      preferred_supplier_id: formState.preferred_supplier_id
        ? Number(formState.preferred_supplier_id)
        : null,
      lead_time_days: formState.lead_time_days.trim()
        ? Number(formState.lead_time_days)
        : null,
    };

    try {
      if (editingProduct) {
        await apiRequest(`/products/${editingProduct.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setFeedback(`Produto "${payload.name}" atualizado com sucesso.`);
      } else {
        await apiRequest("/products", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setFeedback(
          `Produto "${payload.name}" cadastrado com saldo inicial 0. Utilize "Entrada" para registrar estoque.`
        );
      }
      setFormOpen(false);
      await loadProducts();
    } catch (err) {
      setFormSubmitError(
        err instanceof ApiError ? err.message : "Erro ao salvar produto."
      );
    } finally {
      setSavingProduct(false);
    }
  };

  const handleToggleStatus = async () => {
    if (!toggleTarget) return;
    setToggling(true);
    try {
      const nextStatus = !toggleTarget.is_active;
      await apiRequest(`/products/${toggleTarget.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: nextStatus }),
      });
      setFeedback(
        `Produto "${toggleTarget.name}" ${
          nextStatus ? "reativado" : "inativado"
        } com sucesso.`
      );
      setToggleTarget(null);
      await loadProducts();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível alterar o status."
      );
    } finally {
      setToggling(false);
    }
  };

  const openMovementForProduct = (mode: MovementModalMode, productId: number) => {
    setMvMode(mode);
    setMvProductId(productId);
    setMvOpen(true);
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Produtos e Saldos</h1>
          <p className="page-subtitle">
            Consulte saldos disponíveis, cadastre novos itens e realize entradas ou saídas rápidas.
          </p>
        </div>
        {isAdmin ? (
          <div className="header-actions">
            <button type="button" className="btn btn-primary" onClick={openCreateModal}>
              <Plus size={16} />
              <span>Novo Produto</span>
            </button>
          </div>
        ) : null}
      </div>

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

      <div className="card">
        <div className="filters-bar">
          <div className="form-field" style={{ flex: "1 1 240px" }}>
            <label htmlFor="prod-search">Pesquisar (nome, SKU, código de barras ou local)</label>
            <div style={{ position: "relative" }}>
              <input
                id="prod-search"
                type="search"
                className="input"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="Digite para filtrar..."
              />
            </div>
          </div>

          <div className="form-field" style={{ minWidth: 170 }}>
            <label htmlFor="prod-cat-filter">Categoria</label>
            <select
              id="prod-cat-filter"
              className="select"
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todas</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-field" style={{ minWidth: 165 }}>
            <label htmlFor="prod-stock-filter">Situação do Saldo</label>
            <select
              id="prod-stock-filter"
              className="select"
              value={stockFilter}
              onChange={(e) => {
                setStockFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todas</option>
              <option value="OUT_OF_STOCK">Sem estoque</option>
              <option value="BELOW_MIN">Abaixo do mínimo</option>
              <option value="OK">Saldo normal</option>
            </select>
          </div>

          <div className="form-field" style={{ minWidth: 140 }}>
            <label htmlFor="prod-status-filter">Status</label>
            <select
              id="prod-status-filter"
              className="select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="true">Ativos</option>
              <option value="false">Inativos</option>
              <option value="">Todos</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="state-box">Carregando produtos...</div>
        ) : products.length === 0 ? (
          <div className="state-box">
            <Search size={28} />
            <p>Nenhum produto encontrado para os filtros aplicados.</p>
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>SKU / Cód. Barras</th>
                    <th>Produto / Categoria</th>
                    <th>Saldo Atual</th>
                    <th>Mínimo</th>
                    <th>Custo Ref.</th>
                    <th>Localização</th>
                    <th>Status</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((prod) => (
                    <tr key={prod.id}>
                      <td>
                        <div className="mono">
                          <strong>{prod.sku}</strong>
                        </div>
                        {prod.barcode ? (
                          <div className="mono" style={{ color: "#64748b", fontSize: "0.78rem" }}>
                            {prod.barcode}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <strong>{prod.name}</strong>
                        <div style={{ fontSize: "0.78rem", color: "#64748b" }}>
                          {prod.category_name} · Atualizado em {formatDateTimeBR(prod.updated_at)}
                        </div>
                      </td>
                      <td>
                        <strong style={{ fontSize: "1rem" }}>
                          {formatQuantity(prod.current_stock, prod.unit)} {prod.unit}
                        </strong>
                        <div>
                          <span
                            className={`badge ${
                              prod.stock_status === "OUT_OF_STOCK"
                                ? "badge-danger"
                                : prod.stock_status === "BELOW_MIN"
                                ? "badge-warning"
                                : "badge-success"
                            }`}
                          >
                            {translateStockStatus(prod.stock_status)}
                          </span>
                        </div>
                      </td>
                      <td>
                        {formatQuantity(prod.min_stock, prod.unit)} {prod.unit}
                      </td>
                      <td>{formatCurrencyBRL(prod.unit_cost)}</td>
                      <td>{prod.location || "—"}</td>
                      <td>
                        <span
                          className={`badge ${
                            prod.is_active ? "badge-info" : "badge-neutral"
                          }`}
                        >
                          {prod.is_active ? "Ativo" : "Inativo"}
                        </span>
                      </td>
                      <td>
                        <div className="td-actions">
                          {prod.is_active ? (
                            <>
                              <button
                                type="button"
                                className="btn btn-success btn-sm"
                                onClick={() => openMovementForProduct("ENTRADA", prod.id)}
                              >
                                <ArrowDownLeft size={14} />
                                <span>Entrada</span>
                              </button>
                              <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={() => openMovementForProduct("SAIDA", prod.id)}
                              >
                                <ArrowUpRight size={14} />
                                <span>Saída</span>
                              </button>
                            </>
                          ) : null}

                          {isAdmin ? (
                            <>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => openEditModal(prod)}
                              >
                                <Pencil size={14} />
                                <span>Editar</span>
                              </button>
                              <button
                                type="button"
                                className="btn btn-outline-danger btn-sm"
                                onClick={() => setToggleTarget(prod)}
                              >
                                {prod.is_active ? (
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
                            </>
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

      {/* Modal de cadastro / edição */}
      <Modal
        isOpen={formOpen}
        onClose={() => setFormOpen(false)}
        title={editingProduct ? `Editar Produto: ${editingProduct.sku}` : "Cadastrar Novo Produto"}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setFormOpen(false)}
              disabled={savingProduct}
            >
              Cancelar
            </button>
            <button
              type="submit"
              form="product-form"
              className="btn btn-primary"
              disabled={savingProduct}
            >
              <CheckCircle2 size={16} />
              <span>{savingProduct ? "Salvando..." : "Salvar Produto"}</span>
            </button>
          </>
        }
      >
        {!editingProduct ? (
          <div className="alert alert-info" style={{ marginBottom: 14 }}>
            Todo produto cadastrado inicia com <strong>saldo 0</strong>. Caso já exista estoque físico,
            registre em seguida uma movimentação de Entrada com motivo <em>Saldo inicial</em>.
          </div>
        ) : null}

        {formSubmitError ? (
          <div className="alert alert-error" role="alert">
            {formSubmitError}
          </div>
        ) : null}

        <form id="product-form" onSubmit={handleSaveProduct} className="form-grid">
          <div className="form-field full">
            <label htmlFor="pf-name">Nome do Produto *</label>
            <input
              id="pf-name"
              type="text"
              className={`input ${formErrors.name ? "has-error" : ""}`}
              value={formState.name}
              onChange={(e) => setFormState({ ...formState, name: e.target.value })}
              placeholder="Ex: Papel Sulfite A4 75g"
            />
            {formErrors.name ? <span className="field-error">{formErrors.name}</span> : null}
          </div>

          <div className="form-field">
            <label htmlFor="pf-sku">SKU (único) *</label>
            <input
              id="pf-sku"
              type="text"
              className={`input mono ${formErrors.sku ? "has-error" : ""}`}
              value={formState.sku}
              onChange={(e) => setFormState({ ...formState, sku: e.target.value.toUpperCase() })}
              placeholder="Ex: PAP-A4-500"
            />
            {formErrors.sku ? <span className="field-error">{formErrors.sku}</span> : null}
          </div>

          <div className="form-field">
            <label htmlFor="pf-barcode">Código de Barras (opcional e único)</label>
            <input
              id="pf-barcode"
              type="text"
              className="input mono"
              value={formState.barcode}
              onChange={(e) => setFormState({ ...formState, barcode: e.target.value })}
              placeholder="Ex: 7891234567890"
            />
          </div>

          <div className="form-field">
            <label htmlFor="pf-category">Categoria *</label>
            <select
              id="pf-category"
              className={`select ${formErrors.category_id ? "has-error" : ""}`}
              value={formState.category_id}
              onChange={(e) => setFormState({ ...formState, category_id: e.target.value })}
            >
              <option value="">Selecione...</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} {!c.is_active ? "(Inativa)" : ""}
                </option>
              ))}
            </select>
            {formErrors.category_id ? (
              <span className="field-error">{formErrors.category_id}</span>
            ) : null}
          </div>

          <div className="form-field">
            <label htmlFor="pf-unit">Unidade de Medida *</label>
            <select
              id="pf-unit"
              className="select"
              value={formState.unit}
              disabled={Boolean(editingProduct?.has_movements)}
              onChange={(e) => setFormState({ ...formState, unit: e.target.value })}
            >
              {units.map((u) => (
                <option key={u.code} value={u.code}>
                  {u.code} — {u.label} ({u.allow_decimal ? "decimal" : "inteiro"})
                </option>
              ))}
            </select>
            {editingProduct?.has_movements ? (
              <span className="form-hint">
                Unidade bloqueada porque este produto já possui histórico de movimentações.
              </span>
            ) : null}
          </div>

          <div className="form-field">
            <label htmlFor="pf-cost">Custo Unitário de Referência (R$) *</label>
            <input
              id="pf-cost"
              type="number"
              min="0"
              step="0.01"
              className={`input ${formErrors.unit_cost ? "has-error" : ""}`}
              value={formState.unit_cost}
              onChange={(e) => setFormState({ ...formState, unit_cost: e.target.value })}
            />
            {formErrors.unit_cost ? (
              <span className="field-error">{formErrors.unit_cost}</span>
            ) : null}
          </div>

          <div className="form-field">
            <label htmlFor="pf-min">Estoque Mínimo *</label>
            <input
              id="pf-min"
              type="number"
              min="0"
              step={isDiscreteUnitCode(formState.unit) ? "1" : "0.001"}
              className={`input ${formErrors.min_stock ? "has-error" : ""}`}
              value={formState.min_stock}
              onChange={(e) => setFormState({ ...formState, min_stock: e.target.value })}
            />
            {formErrors.min_stock ? (
              <span className="field-error">{formErrors.min_stock}</span>
            ) : null}
          </div>

          <div className="form-field">
            <label htmlFor="pf-safety">Estoque de Segurança (para IA)</label>
            <input
              id="pf-safety"
              type="number"
              min="0"
              step={isDiscreteUnitCode(formState.unit) ? "1" : "0.001"}
              className={`input ${formErrors.safety_stock ? "has-error" : ""}`}
              value={formState.safety_stock}
              onChange={(e) => setFormState({ ...formState, safety_stock: e.target.value })}
            />
            {formErrors.safety_stock ? (
              <span className="field-error">{formErrors.safety_stock}</span>
            ) : null}
          </div>

          <div className="form-field">
            <label htmlFor="pf-location">Localização Física (opcional)</label>
            <input
              id="pf-location"
              type="text"
              className="input"
              value={formState.location}
              onChange={(e) => setFormState({ ...formState, location: e.target.value })}
              placeholder="Ex: Corredor A, Prateleira 3"
            />
          </div>

          <div className="form-field">
            <label htmlFor="pf-supplier">Fornecedor Preferencial (opcional)</label>
            <select
              id="pf-supplier"
              className="select"
              value={formState.preferred_supplier_id}
              onChange={(e) =>
                setFormState({ ...formState, preferred_supplier_id: e.target.value })
              }
            >
              <option value="">Nenhum selecionado</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-field">
            <label htmlFor="pf-leadtime">Prazo Estimado de Reposição (dias)</label>
            <input
              id="pf-leadtime"
              type="number"
              min="0"
              step="1"
              className={`input ${formErrors.lead_time_days ? "has-error" : ""}`}
              value={formState.lead_time_days}
              onChange={(e) => setFormState({ ...formState, lead_time_days: e.target.value })}
              placeholder="Ex: 7"
            />
            {formErrors.lead_time_days ? (
              <span className="field-error">{formErrors.lead_time_days}</span>
            ) : null}
          </div>

          <div className="form-field full">
            <label htmlFor="pf-desc">Descrição (opcional)</label>
            <textarea
              id="pf-desc"
              className="textarea"
              value={formState.description}
              onChange={(e) => setFormState({ ...formState, description: e.target.value })}
              placeholder="Especificações técnicas ou observações de armazenagem..."
            />
          </div>
        </form>
      </Modal>

      <ConfirmModal
        isOpen={Boolean(toggleTarget)}
        onClose={() => setToggleTarget(null)}
        onConfirm={handleToggleStatus}
        title={toggleTarget?.is_active ? "Inativar Produto" : "Reativar Produto"}
        description={
          toggleTarget?.is_active
            ? `Ao inativar "${toggleTarget?.name}", todo o histórico de movimentações será preservado, mas novas entradas e saídas serão bloqueadas.`
            : `Deseja reativar "${toggleTarget?.name}" para permitir novas movimentações?`
        }
        confirmLabel={toggleTarget?.is_active ? "Confirmar Inativação" : "Confirmar Reativação"}
        confirmVariant={toggleTarget?.is_active ? "danger" : "primary"}
        isSubmitting={toggling}
      />

      <MovementModal
        isOpen={mvOpen}
        mode={mvMode}
        products={products}
        suppliers={suppliers}
        initialProductId={mvProductId}
        onClose={() => setMvOpen(false)}
        onSuccess={(msg) => {
          setFeedback(msg);
          loadProducts();
        }}
      />
    </div>
  );
}
