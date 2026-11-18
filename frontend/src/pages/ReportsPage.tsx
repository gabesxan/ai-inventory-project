import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { Pagination } from "../components/Pagination";
import {
  apiRequest,
  ApiError,
  buildQueryString,
  downloadAuthenticatedFile,
} from "../services/api";
import type {
  Category,
  MovementResponsible,
  PaginatedResponse,
  Product,
  StockMovement,
} from "../types/api";
import {
  formatCurrencyBRL,
  formatDateTimeBR,
  formatQuantity,
  translateMovementType,
  translateReasonCode,
  translateStockStatus,
} from "../utils/format";

type ReportTab = "current-stock" | "below-minimum" | "movements";

export function ReportsPage() {
  const [tab, setTab] = useState<ReportTab>("current-stock");
  const [categories, setCategories] = useState<Category[]>([]);
  const [productsList, setProductsList] = useState<Product[]>([]);
  const [responsibles, setResponsibles] = useState<MovementResponsible[]>([]);

  // Filtros compartilhados / específicos
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [isActive, setIsActive] = useState("true");
  const [productId, setProductId] = useState("");
  const [movementType, setMovementType] = useState("");
  const [userId, setUserId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  const [stockRows, setStockRows] = useState<Product[]>([]);
  const [movementRows, setMovementRows] = useState<StockMovement[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiRequest<PaginatedResponse<Category>>("/categories?page_size=200"),
      apiRequest<PaginatedResponse<Product>>("/products?page_size=200"),
      apiRequest<MovementResponsible[]>("/movements/responsibles"),
    ])
      .then(([catRes, prodRes, respRes]) => {
        setCategories(catRes.items);
        setProductsList(prodRes.items);
        setResponsibles(respRes);
      })
      .catch(() => {});
  }, []);

  const buildActiveParams = useCallback(() => {
    if (tab === "current-stock") {
      return {
        search: search.trim() || undefined,
        category_id: categoryId || undefined,
        is_active: isActive === "" ? undefined : isActive,
      };
    }
    if (tab === "below-minimum") {
      return {
        search: search.trim() || undefined,
        category_id: categoryId || undefined,
      };
    }
    return {
      search: search.trim() || undefined,
      product_id: productId || undefined,
      movement_type: movementType || undefined,
      user_id: userId || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    };
  }, [tab, search, categoryId, isActive, productId, movementType, userId, startDate, endDate]);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { ...buildActiveParams(), page, page_size: 20 };
      const qs = buildQueryString(params);
      if (tab === "movements") {
        const res = await apiRequest<PaginatedResponse<StockMovement>>(
          `/reports/movements${qs}`
        );
        setMovementRows(res.items);
        setTotal(res.total);
        setTotalPages(res.total_pages);
      } else {
        const endpoint =
          tab === "current-stock"
            ? "/reports/current-stock"
            : "/reports/below-minimum";
        const res = await apiRequest<PaginatedResponse<Product>>(`${endpoint}${qs}`);
        setStockRows(res.items);
        setTotal(res.total);
        setTotalPages(res.total_pages);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erro ao gerar relatório.");
    } finally {
      setLoading(false);
    }
  }, [tab, page, buildActiveParams]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const handleExportCsv = async () => {
    setExporting(true);
    setError(null);
    try {
      const qs = buildQueryString({ ...buildActiveParams(), export: "csv" });
      const endpoint =
        tab === "current-stock"
          ? `/reports/current-stock${qs}`
          : tab === "below-minimum"
          ? `/reports/below-minimum${qs}`
          : `/reports/movements${qs}`;
      const filename =
        tab === "current-stock"
          ? "relatorio_estoque_atual.csv"
          : tab === "below-minimum"
          ? "relatorio_abaixo_minimo.csv"
          : "relatorio_movimentacoes.csv";
      await downloadAuthenticatedFile(endpoint, filename);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Falha ao exportar relatório CSV."
      );
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Relatórios Gerenciais</h1>
          <p className="page-subtitle">
            Consulte os relatórios filtrados e exporte em CSV exatamente o recorte exibido.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleExportCsv}
            disabled={exporting}
          >
            <Download size={16} />
            <span>{exporting ? "Exportando..." : "Exportar CSV"}</span>
          </button>
        </div>
      </div>

      {error ? (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      ) : null}

      <div className="tabs-bar">
        <button
          type="button"
          className={`tab-btn ${tab === "current-stock" ? "active" : ""}`}
          onClick={() => {
            setTab("current-stock");
            setPage(1);
          }}
        >
          Estoque Atual
        </button>
        <button
          type="button"
          className={`tab-btn ${tab === "below-minimum" ? "active" : ""}`}
          onClick={() => {
            setTab("below-minimum");
            setPage(1);
          }}
        >
          Produtos Abaixo do Mínimo
        </button>
        <button
          type="button"
          className={`tab-btn ${tab === "movements" ? "active" : ""}`}
          onClick={() => {
            setTab("movements");
            setPage(1);
          }}
        >
          Histórico de Movimentações
        </button>
      </div>

      <div className="card">
        <div className="filters-bar">
          <div className="form-field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="rep-search">Pesquisar</label>
            <input
              id="rep-search"
              type="search"
              className="input"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="SKU, nome..."
            />
          </div>

          {tab !== "movements" ? (
            <>
              <div className="form-field" style={{ minWidth: 180 }}>
                <label htmlFor="rep-cat">Categoria</label>
                <select
                  id="rep-cat"
                  className="select"
                  value={categoryId}
                  onChange={(e) => {
                    setCategoryId(e.target.value);
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
              {tab === "current-stock" ? (
                <div className="form-field" style={{ minWidth: 140 }}>
                  <label htmlFor="rep-status">Status</label>
                  <select
                    id="rep-status"
                    className="select"
                    value={isActive}
                    onChange={(e) => {
                      setIsActive(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="true">Ativos</option>
                    <option value="false">Inativos</option>
                    <option value="">Todos</option>
                  </select>
                </div>
              ) : null}
            </>
          ) : (
            <>
              <div className="form-field" style={{ minWidth: 190 }}>
                <label htmlFor="rep-prod">Produto</label>
                <select
                  id="rep-prod"
                  className="select"
                  value={productId}
                  onChange={(e) => {
                    setProductId(e.target.value);
                    setPage(1);
                  }}
                >
                  <option value="">Todos</option>
                  {productsList.map((p) => (
                    <option key={p.id} value={p.id}>
                      [{p.sku}] {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-field" style={{ minWidth: 145 }}>
                <label htmlFor="rep-type">Tipo</label>
                <select
                  id="rep-type"
                  className="select"
                  value={movementType}
                  onChange={(e) => {
                    setMovementType(e.target.value);
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
              <div className="form-field" style={{ minWidth: 165 }}>
                <label htmlFor="rep-user">Responsável</label>
                <select
                  id="rep-user"
                  className="select"
                  value={userId}
                  onChange={(e) => {
                    setUserId(e.target.value);
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
                <label htmlFor="rep-start">De</label>
                <input
                  id="rep-start"
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
                <label htmlFor="rep-end">Até</label>
                <input
                  id="rep-end"
                  type="date"
                  className="input"
                  value={endDate}
                  onChange={(e) => {
                    setEndDate(e.target.value);
                    setPage(1);
                  }}
                />
              </div>
            </>
          )}
        </div>

        {loading ? (
          <div className="state-box">Carregando dados do relatório...</div>
        ) : tab !== "movements" ? (
          stockRows.length === 0 ? (
            <div className="state-box">Nenhum produto encontrado para este relatório.</div>
          ) : (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Produto</th>
                      <th>Categoria</th>
                      <th>Saldo Atual</th>
                      <th>Mínimo</th>
                      <th>Custo Ref.</th>
                      <th>Valor Estimado (Ref.)</th>
                      <th>Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stockRows.map((p) => (
                      <tr key={p.id}>
                        <td className="mono">{p.sku}</td>
                        <td>
                          <strong>{p.name}</strong>
                        </td>
                        <td>{p.category_name}</td>
                        <td>
                          <strong>
                            {formatQuantity(p.current_stock, p.unit)} {p.unit}
                          </strong>
                        </td>
                        <td>
                          {formatQuantity(p.min_stock, p.unit)} {p.unit}
                        </td>
                        <td>{formatCurrencyBRL(p.unit_cost)}</td>
                        <td>{formatCurrencyBRL(p.estimated_total_value)}</td>
                        <td>
                          <span
                            className={`badge ${
                              p.stock_status === "OUT_OF_STOCK"
                                ? "badge-danger"
                                : p.stock_status === "BELOW_MIN"
                                ? "badge-warning"
                                : "badge-success"
                            }`}
                          >
                            {translateStockStatus(p.stock_status)}
                          </span>
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
          )
        ) : movementRows.length === 0 ? (
          <div className="state-box">Nenhuma movimentação encontrada para este relatório.</div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Data/Hora</th>
                    <th>SKU / Produto</th>
                    <th>Tipo</th>
                    <th>Motivo</th>
                    <th>Quantidade</th>
                    <th>Saldo Final</th>
                    <th>Responsável</th>
                  </tr>
                </thead>
                <tbody>
                  {movementRows.map((m) => (
                    <tr key={m.id}>
                      <td>{formatDateTimeBR(m.created_at)}</td>
                      <td>
                        <span className="mono">{m.product_sku}</span> — {m.product_name}
                      </td>
                      <td>{translateMovementType(m.movement_type)}</td>
                      <td>{translateReasonCode(m.reason_code)}</td>
                      <td>
                        {Number(m.signed_quantity) > 0 ? "+" : "-"}
                        {formatQuantity(m.quantity, m.unit_snapshot)} {m.unit_snapshot}
                      </td>
                      <td>
                        {formatQuantity(m.balance_after, m.unit_snapshot)}{" "}
                        {m.unit_snapshot}
                      </td>
                      <td>{m.user_name}</td>
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
    </div>
  );
}
