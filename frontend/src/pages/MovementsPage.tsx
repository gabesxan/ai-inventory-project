import { useCallback, useEffect, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import { ConfirmModal } from "../components/ConfirmModal";
import { MovementModal, type MovementModalMode } from "../components/MovementModal";
import { Pagination } from "../components/Pagination";
import { useAuth } from "../context/AuthContext";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type {
  MovementResponsible,
  PaginatedResponse,
  Product,
  StockMovement,
  Supplier,
} from "../types/api";
import {
  formatCurrencyBRL,
  formatDateBR,
  formatDateTimeBR,
  formatQuantity,
  translateMovementType,
  translateReasonCode,
} from "../utils/format";

export function MovementsPage() {
  const { isAdmin } = useAuth();

  const [movements, setMovements] = useState<StockMovement[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);

  const [products, setProducts] = useState<Product[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [responsibles, setResponsibles] = useState<MovementResponsible[]>([]);

  // Filtros
  const [search, setSearch] = useState("");
  const [productFilter, setProductFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [mvOpen, setMvOpen] = useState(false);
  const [mvMode, setMvMode] = useState<MovementModalMode>("ENTRADA");

  const [reverseTarget, setReverseTarget] = useState<StockMovement | null>(null);
  const [reversing, setReversing] = useState(false);
  const [reverseError, setReverseError] = useState<string | null>(null);

  const loadReferenceLists = useCallback(async () => {
    try {
      const [prodRes, supRes, respRes] = await Promise.all([
        apiRequest<PaginatedResponse<Product>>("/products?page_size=200"),
        apiRequest<PaginatedResponse<Supplier>>("/suppliers?page_size=200"),
        apiRequest<MovementResponsible[]>("/movements/responsibles"),
      ]);
      setProducts(prodRes.items);
      setSuppliers(supRes.items);
      setResponsibles(respRes);
    } catch {
      // ignora erro secundário
    }
  }, []);

  const loadMovements = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({
        search: search.trim() || undefined,
        product_id: productFilter || undefined,
        movement_type: typeFilter || undefined,
        user_id: userFilter || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        page,
        page_size: 20,
      });
      const res = await apiRequest<PaginatedResponse<StockMovement>>(
        `/movements${qs}`
      );
      setMovements(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Erro ao carregar histórico de movimentações."
      );
    } finally {
      setLoading(false);
    }
  }, [search, productFilter, typeFilter, userFilter, startDate, endDate, page]);

  useEffect(() => {
    loadReferenceLists();
  }, [loadReferenceLists]);

  useEffect(() => {
    loadMovements();
  }, [loadMovements]);

  const handleOpenMovementModal = (mode: MovementModalMode) => {
    setMvMode(mode);
    setMvOpen(true);
  };

  const handleReverseConfirm = async (reason: string) => {
    if (!reverseTarget) return;
    setReversing(true);
    setReverseError(null);
    try {
      await apiRequest(`/movements/${reverseTarget.id}/reverse`, {
        method: "POST",
        body: JSON.stringify({ notes: reason }),
      });
      setFeedback(
        `Movimentação #${reverseTarget.id} estornada com sucesso (lançamento inverso gerado).`
      );
      setReverseTarget(null);
      await Promise.all([loadMovements(), loadReferenceLists()]);
    } catch (err) {
      setReverseError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível estornar a movimentação."
      );
    } finally {
      setReversing(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Movimentações de Estoque</h1>
          <p className="page-subtitle">
            Histórico imutável de entradas, saídas, ajustes e estornos com rastreabilidade completa.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-success"
            onClick={() => handleOpenMovementModal("ENTRADA")}
          >
            <ArrowDownLeft size={16} />
            <span>Registrar Entrada</span>
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => handleOpenMovementModal("SAIDA")}
          >
            <ArrowUpRight size={16} />
            <span>Registrar Saída</span>
          </button>
          {isAdmin ? (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => handleOpenMovementModal("AJUSTE")}
            >
              <SlidersHorizontal size={16} />
              <span>Registrar Ajuste</span>
            </button>
          ) : null}
        </div>
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
          <div className="form-field" style={{ flex: "1 1 210px" }}>
            <label htmlFor="mv-filter-search">Pesquisar (SKU, produto, usuário ou obs.)</label>
            <input
              id="mv-filter-search"
              type="search"
              className="input"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Buscar no histórico..."
            />
          </div>

          <div className="form-field" style={{ minWidth: 190 }}>
            <label htmlFor="mv-filter-prod">Produto</label>
            <select
              id="mv-filter-prod"
              className="select"
              value={productFilter}
              onChange={(e) => {
                setProductFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos os produtos</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  [{p.sku}] {p.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-field" style={{ minWidth: 150 }}>
            <label htmlFor="mv-filter-type">Tipo</label>
            <select
              id="mv-filter-type"
              className="select"
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos</option>
              <option value="ENTRADA">Entrada</option>
              <option value="SAIDA">Saída</option>
              <option value="AJUSTE">Ajuste</option>
              <option value="ESTORNO">Estorno</option>
            </select>
          </div>

          <div className="form-field" style={{ minWidth: 170 }}>
            <label htmlFor="mv-filter-user">Responsável</label>
            <select
              id="mv-filter-user"
              className="select"
              value={userFilter}
              onChange={(e) => {
                setUserFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Todos</option>
              {responsibles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-field">
            <label htmlFor="mv-filter-start">De</label>
            <input
              id="mv-filter-start"
              type="date"
              className="input"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPage(1);
              }}
            />
          </div>

          <div className="form-field">
            <label htmlFor="mv-filter-end">Até</label>
            <input
              id="mv-filter-end"
              type="date"
              className="input"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>

        {loading ? (
          <div className="state-box">Carregando histórico de movimentações...</div>
        ) : movements.length === 0 ? (
          <div className="state-box">
            Nenhuma movimentação encontrada para os filtros selecionados.
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Data/Hora</th>
                    <th>Produto</th>
                    <th>Tipo / Motivo</th>
                    <th>Quantidade</th>
                    <th>Saldo (Antes → Depois)</th>
                    <th>Custo / Fornecedor</th>
                    <th>Responsável / Obs.</th>
                    {isAdmin ? <th>Ações</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {movements.map((mv) => {
                    const isPositive = Number(mv.signed_quantity) > 0;
                    const badgeClass =
                      mv.movement_type === "ENTRADA"
                        ? "badge-success"
                        : mv.movement_type === "SAIDA"
                        ? "badge-info"
                        : mv.movement_type === "AJUSTE"
                        ? "badge-warning"
                        : "badge-danger";

                    return (
                      <tr key={mv.id}>
                        <td>
                          <div>{formatDateTimeBR(mv.created_at)}</div>
                          <div className="mono" style={{ color: "#64748b", fontSize: "0.76rem" }}>
                            #{mv.id}
                            {mv.reference_movement_id
                              ? ` (ref. #${mv.reference_movement_id})`
                              : ""}
                          </div>
                        </td>
                        <td>
                          <strong>{mv.product_name}</strong>
                          <div className="mono" style={{ fontSize: "0.78rem", color: "#64748b" }}>
                            {mv.product_sku}
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${badgeClass}`}>
                            {translateMovementType(mv.movement_type)}
                          </span>
                          <div style={{ fontSize: "0.82rem", marginTop: 4 }}>
                            {translateReasonCode(mv.reason_code)}
                            {mv.is_demand ? (
                              <span
                                className="badge badge-neutral"
                                style={{ marginLeft: 6 }}
                              >
                                Demanda IA
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td>
                          <strong
                            style={{
                              color: isPositive ? "#15803d" : "#b91c1c",
                            }}
                          >
                            {isPositive ? "+" : "-"}
                            {formatQuantity(mv.quantity, mv.unit_snapshot)}{" "}
                            {mv.unit_snapshot}
                          </strong>
                        </td>
                        <td>
                          {formatQuantity(mv.balance_before, mv.unit_snapshot)} →{" "}
                          <strong>
                            {formatQuantity(mv.balance_after, mv.unit_snapshot)}{" "}
                            {mv.unit_snapshot}
                          </strong>
                        </td>
                        <td>
                          {mv.unit_cost !== null ? (
                            <div>Custo: {formatCurrencyBRL(mv.unit_cost)}</div>
                          ) : null}
                          {mv.supplier_name ? (
                            <div style={{ fontSize: "0.8rem", color: "#475569" }}>
                              {mv.supplier_name}
                            </div>
                          ) : null}
                          {mv.order_date || mv.received_date ? (
                            <div style={{ fontSize: "0.76rem", color: "#64748b" }}>
                              Ped: {formatDateBR(mv.order_date)} · Rec:{" "}
                              {formatDateBR(mv.received_date)}
                              {mv.actual_lead_time_days !== null
                                ? ` (${mv.actual_lead_time_days}d)`
                                : ""}
                            </div>
                          ) : null}
                          {mv.unit_cost === null && !mv.supplier_name ? "—" : null}
                        </td>
                        <td>
                          <div>
                            <strong>{mv.user_name}</strong>
                          </div>
                          {mv.notes ? (
                            <div style={{ fontSize: "0.8rem", color: "#475569" }}>
                              {mv.notes}
                            </div>
                          ) : null}
                          {mv.reversed_by_movement_id ? (
                            <span className="badge badge-danger" style={{ marginTop: 4 }}>
                              Estornada pelo #{mv.reversed_by_movement_id}
                            </span>
                          ) : null}
                        </td>
                        {isAdmin ? (
                          <td>
                            {mv.movement_type !== "ESTORNO" &&
                            !mv.reversed_by_movement_id ? (
                              <button
                                type="button"
                                className="btn btn-outline-danger btn-sm"
                                onClick={() => {
                                  setReverseError(null);
                                  setReverseTarget(mv);
                                }}
                              >
                                <RotateCcw size={14} />
                                <span>Estornar</span>
                              </button>
                            ) : (
                              <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                                —
                              </span>
                            )}
                          </td>
                        ) : null}
                      </tr>
                    );
                  })}
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

      <MovementModal
        isOpen={mvOpen}
        mode={mvMode}
        products={products}
        suppliers={suppliers}
        onClose={() => setMvOpen(false)}
        onSuccess={(msg) => {
          setFeedback(msg);
          setPage(1);
          loadMovements();
          loadReferenceLists();
        }}
      />

      <ConfirmModal
        isOpen={Boolean(reverseTarget)}
        onClose={() => setReverseTarget(null)}
        onConfirm={handleReverseConfirm}
        title={`Estornar Movimentação #${reverseTarget?.id ?? ""}`}
        description={
          reverseTarget
            ? `Esta ação criará uma movimentação inversa vinculada ao lançamento #${reverseTarget.id} (${translateMovementType(reverseTarget.movement_type)} de ${formatQuantity(reverseTarget.quantity, reverseTarget.unit_snapshot)} ${reverseTarget.unit_snapshot} em ${reverseTarget.product_name}). A movimentação original não será apagada.`
            : ""
        }
        confirmLabel="Confirmar Estorno"
        confirmVariant="danger"
        requireReason
        reasonLabel="Justificativa do estorno *"
        reasonPlaceholder="Explique o motivo do estorno (ex: lançamento duplicado ou erro de conferência)..."
        isSubmitting={reversing}
        errorMessage={reverseError}
      />
    </div>
  );
}
