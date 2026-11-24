import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Download, RotateCcw } from "lucide-react";
import { Pagination } from "../components/Pagination";
import {
  apiRequest,
  ApiError,
  buildQueryString,
  downloadAuthenticatedFile,
} from "../services/api";
import type {
  Category,
  ImportedHistoryRow,
  MovementResponsible,
  PaginatedResponse,
  Product,
  ReplenishmentRow,
  StockMovement,
  VersionedReport,
} from "../types/api";
import {
  formatCurrencyBRL,
  formatDateBR,
  formatDateTimeBR,
  formatQuantity,
  translateMovementType,
  translateReasonCode,
  translateStockStatus,
} from "../utils/format";

export type ReportTab =
  | "current-stock"
  | "below-minimum"
  | "movements"
  | "imported-history"
  | "replenishment";

const REPORT_TABS: Array<{ id: ReportTab; label: string; supportsCsv: boolean }> = [
  { id: "current-stock", label: "Estoque Atual", supportsCsv: true },
  { id: "below-minimum", label: "Abaixo do Mínimo", supportsCsv: true },
  { id: "movements", label: "Movimentações", supportsCsv: true },
  { id: "imported-history", label: "Histórico Importado", supportsCsv: true },
  { id: "replenishment", label: "Reposição", supportsCsv: false },
];

function parseTabParam(raw: string | null): ReportTab {
  if (
    raw === "current-stock" ||
    raw === "below-minimum" ||
    raw === "movements" ||
    raw === "imported-history" ||
    raw === "replenishment"
  ) {
    return raw;
  }
  return "current-stock";
}

interface CurrentStockFilters {
  search: string;
  category_id: string;
  is_active: string;
}

interface BelowMinimumFilters {
  search: string;
  category_id: string;
}

interface MovementsFilters {
  search: string;
  product_id: string;
  movement_type: string;
  user_id: string;
  start_date: string;
  end_date: string;
}

interface ImportedHistoryFilters {
  sku: string;
  warehouse: string;
  event_type: string;
  start_date: string;
  end_date: string;
}

interface ReplenishmentFilters {
  sku: string;
  warehouse: string;
}

const DEFAULT_CURRENT_STOCK_FILTERS: CurrentStockFilters = {
  search: "",
  category_id: "",
  is_active: "true",
};

const DEFAULT_BELOW_MIN_FILTERS: BelowMinimumFilters = {
  search: "",
  category_id: "",
};

const DEFAULT_MOVEMENTS_FILTERS: MovementsFilters = {
  search: "",
  product_id: "",
  movement_type: "",
  user_id: "",
  start_date: "",
  end_date: "",
};

const DEFAULT_IMPORTED_HISTORY_FILTERS: ImportedHistoryFilters = {
  sku: "",
  warehouse: "",
  event_type: "",
  start_date: "",
  end_date: "",
};

const DEFAULT_REPLENISHMENT_FILTERS: ReplenishmentFilters = {
  sku: "",
  warehouse: "",
};

function translateImportedEventType(eventType: string): string {
  const map: Record<string, string> = {
    sale: "Venda",
    receipt: "Recebimento",
    return: "Devolução",
    other_outbound: "Outra saída",
    adjustment: "Ajuste",
  };
  return map[eventType] ?? eventType;
}

function translateCoverageStatus(status: string): string {
  const map: Record<string, string> = {
    available: "Disponível",
    stockout: "Ruptura",
    unknown: "Desconhecida",
    uncovered: "Sem cobertura",
  };
  return map[status] ?? status;
}

export function ReportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTabParam(searchParams.get("tab"));

  const [categories, setCategories] = useState<Category[]>([]);
  const [productsList, setProductsList] = useState<Product[]>([]);
  const [responsibles, setResponsibles] = useState<MovementResponsible[]>([]);

  // Isolated per-tab filter states so filters never leak across tabs
  const [stockFilters, setStockFilters] = useState<CurrentStockFilters>(
    DEFAULT_CURRENT_STOCK_FILTERS
  );
  const [belowMinFilters, setBelowMinFilters] = useState<BelowMinimumFilters>(
    DEFAULT_BELOW_MIN_FILTERS
  );
  const [movementFilters, setMovementFilters] = useState<MovementsFilters>(
    DEFAULT_MOVEMENTS_FILTERS
  );
  const [importedFilters, setImportedFilters] = useState<ImportedHistoryFilters>(
    DEFAULT_IMPORTED_HISTORY_FILTERS
  );
  const [replenishmentFilters, setReplenishmentFilters] = useState<ReplenishmentFilters>(
    DEFAULT_REPLENISHMENT_FILTERS
  );

  const [pageByTab, setPageByTab] = useState<Record<ReportTab, number>>({
    "current-stock": 1,
    "below-minimum": 1,
    movements: 1,
    "imported-history": 1,
    replenishment: 1,
  });

  const page = pageByTab[tab];
  const setPage = useCallback(
    (nextPage: number) => {
      setPageByTab((prev) => ({ ...prev, [tab]: nextPage }));
    },
    [tab]
  );

  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  const [stockRows, setStockRows] = useState<Product[]>([]);
  const [movementRows, setMovementRows] = useState<StockMovement[]>([]);
  const [importedReport, setImportedReport] =
    useState<VersionedReport<ImportedHistoryRow> | null>(null);
  const [replenishmentReport, setReplenishmentReport] =
    useState<VersionedReport<ReplenishmentRow> | null>(null);

  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeTabConfig =
    REPORT_TABS.find((item) => item.id === tab) ?? REPORT_TABS[0];

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

  const handleSelectTab = (nextTab: ReportTab) => {
    if (nextTab === tab) return;
    setError(null);
    setSearchParams({ tab: nextTab });
  };

  const buildActiveParams = useCallback((): Record<
    string,
    string | number | boolean | undefined
  > => {
    switch (tab) {
      case "current-stock":
        return {
          search: stockFilters.search.trim() || undefined,
          category_id: stockFilters.category_id || undefined,
          is_active: stockFilters.is_active === "" ? undefined : stockFilters.is_active,
        };
      case "below-minimum":
        return {
          search: belowMinFilters.search.trim() || undefined,
          category_id: belowMinFilters.category_id || undefined,
        };
      case "movements":
        return {
          search: movementFilters.search.trim() || undefined,
          product_id: movementFilters.product_id || undefined,
          movement_type: movementFilters.movement_type || undefined,
          user_id: movementFilters.user_id || undefined,
          start_date: movementFilters.start_date || undefined,
          end_date: movementFilters.end_date || undefined,
        };
      case "imported-history":
        return {
          sku: importedFilters.sku.trim() || undefined,
          warehouse: importedFilters.warehouse.trim() || undefined,
          event_type: importedFilters.event_type || undefined,
          start_date: importedFilters.start_date || undefined,
          end_date: importedFilters.end_date || undefined,
        };
      case "replenishment":
        return {
          sku: replenishmentFilters.sku.trim() || undefined,
          warehouse: replenishmentFilters.warehouse.trim() || undefined,
        };
    }
  }, [
    tab,
    stockFilters,
    belowMinFilters,
    movementFilters,
    importedFilters,
    replenishmentFilters,
  ]);

  const handleResetActiveFilters = () => {
    setPage(1);
    switch (tab) {
      case "current-stock":
        setStockFilters(DEFAULT_CURRENT_STOCK_FILTERS);
        break;
      case "below-minimum":
        setBelowMinFilters(DEFAULT_BELOW_MIN_FILTERS);
        break;
      case "movements":
        setMovementFilters(DEFAULT_MOVEMENTS_FILTERS);
        break;
      case "imported-history":
        setImportedFilters(DEFAULT_IMPORTED_HISTORY_FILTERS);
        break;
      case "replenishment":
        setReplenishmentFilters(DEFAULT_REPLENISHMENT_FILTERS);
        break;
    }
  };

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const pageSize =
        tab === "imported-history" || tab === "replenishment" ? 25 : 20;
      const qs = buildQueryString({
        ...buildActiveParams(),
        page,
        page_size: pageSize,
      });

      if (tab === "current-stock" || tab === "below-minimum") {
        const endpoint =
          tab === "current-stock"
            ? "/reports/current-stock"
            : "/reports/below-minimum";
        const res = await apiRequest<PaginatedResponse<Product>>(`${endpoint}${qs}`);
        setStockRows(res.items);
        setTotal(res.total);
        setTotalPages(res.total_pages);
      } else if (tab === "movements") {
        const res = await apiRequest<PaginatedResponse<StockMovement>>(
          `/reports/movements${qs}`
        );
        setMovementRows(res.items);
        setTotal(res.total);
        setTotalPages(res.total_pages);
      } else if (tab === "imported-history") {
        const res = await apiRequest<VersionedReport<ImportedHistoryRow>>(
          `/reports/imported-history${qs}`
        );
        setImportedReport(res);
        setTotal(res.total);
        setTotalPages(res.total_pages);
      } else {
        const res = await apiRequest<VersionedReport<ReplenishmentRow>>(
          `/reports/replenishment${qs}`
        );
        setReplenishmentReport(res);
        setTotal(res.total);
        setTotalPages(res.total_pages);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Erro ao gerar relatório.");
      if (tab === "imported-history") setImportedReport(null);
      if (tab === "replenishment") setReplenishmentReport(null);
    } finally {
      setLoading(false);
    }
  }, [tab, page, buildActiveParams]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const handleExportCsv = async () => {
    if (!activeTabConfig.supportsCsv) return;
    setExporting(true);
    setError(null);
    try {
      const qs = buildQueryString({ ...buildActiveParams(), export: "csv" });
      const endpointMap: Record<Exclude<ReportTab, "replenishment">, string> = {
        "current-stock": `/reports/current-stock${qs}`,
        "below-minimum": `/reports/below-minimum${qs}`,
        movements: `/reports/movements${qs}`,
        "imported-history": `/reports/imported-history${qs}`,
      };
      const filenameMap: Record<Exclude<ReportTab, "replenishment">, string> = {
        "current-stock": "relatorio_estoque_atual.csv",
        "below-minimum": "relatorio_abaixo_minimo.csv",
        movements: "relatorio_movimentacoes.csv",
        "imported-history": "relatorio_historico_importado.csv",
      };
      const csvTab = tab as Exclude<ReportTab, "replenishment">;
      await downloadAuthenticatedFile(endpointMap[csvTab], filenameMap[csvTab]);
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
          <h1>Relatórios</h1>
          <p className="page-subtitle">
            Consulte posições de estoque, histórico operacional e importado, e recomendações de reposição.
          </p>
        </div>
        <div className="header-actions">
          {activeTabConfig.supportsCsv ? (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleExportCsv}
              disabled={exporting}
            >
              <Download size={15} aria-hidden="true" />
              <span>{exporting ? "Exportando..." : "Exportar CSV"}</span>
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      ) : null}

      <div className="tabs-bar" role="tablist" aria-label="Tipos de relatório">
        {REPORT_TABS.map((item) => {
          const isActive = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`report-tab-${item.id}`}
              aria-selected={isActive}
              aria-controls={`report-panel-${item.id}`}
              className={`tab-btn ${isActive ? "active" : ""}`}
              onClick={() => handleSelectTab(item.id)}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <section
        id={`report-panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`report-tab-${tab}`}
        className="card"
      >
        <div className="filters-bar">
          {tab === "current-stock" ? (
            <>
              <div className="form-field" style={{ flex: "1 1 220px" }}>
                <label htmlFor="rep-stock-search">Pesquisar</label>
                <input
                  id="rep-stock-search"
                  type="search"
                  className="input"
                  value={stockFilters.search}
                  onChange={(e) => {
                    setStockFilters((prev) => ({ ...prev, search: e.target.value }));
                    setPage(1);
                  }}
                  placeholder="SKU ou nome do produto..."
                />
              </div>
              <div className="form-field" style={{ minWidth: 180 }}>
                <label htmlFor="rep-stock-cat">Categoria</label>
                <select
                  id="rep-stock-cat"
                  className="select"
                  value={stockFilters.category_id}
                  onChange={(e) => {
                    setStockFilters((prev) => ({
                      ...prev,
                      category_id: e.target.value,
                    }));
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
              <div className="form-field" style={{ minWidth: 140 }}>
                <label htmlFor="rep-stock-status">Status</label>
                <select
                  id="rep-stock-status"
                  className="select"
                  value={stockFilters.is_active}
                  onChange={(e) => {
                    setStockFilters((prev) => ({ ...prev, is_active: e.target.value }));
                    setPage(1);
                  }}
                >
                  <option value="true">Ativos</option>
                  <option value="false">Inativos</option>
                  <option value="">Todos</option>
                </select>
              </div>
            </>
          ) : null}

          {tab === "below-minimum" ? (
            <>
              <div className="form-field" style={{ flex: "1 1 220px" }}>
                <label htmlFor="rep-min-search">Pesquisar</label>
                <input
                  id="rep-min-search"
                  type="search"
                  className="input"
                  value={belowMinFilters.search}
                  onChange={(e) => {
                    setBelowMinFilters((prev) => ({ ...prev, search: e.target.value }));
                    setPage(1);
                  }}
                  placeholder="SKU ou nome do produto..."
                />
              </div>
              <div className="form-field" style={{ minWidth: 180 }}>
                <label htmlFor="rep-min-cat">Categoria</label>
                <select
                  id="rep-min-cat"
                  className="select"
                  value={belowMinFilters.category_id}
                  onChange={(e) => {
                    setBelowMinFilters((prev) => ({
                      ...prev,
                      category_id: e.target.value,
                    }));
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
            </>
          ) : null}

          {tab === "movements" ? (
            <>
              <div className="form-field" style={{ flex: "1 1 200px" }}>
                <label htmlFor="rep-mv-search">Pesquisar</label>
                <input
                  id="rep-mv-search"
                  type="search"
                  className="input"
                  value={movementFilters.search}
                  onChange={(e) => {
                    setMovementFilters((prev) => ({ ...prev, search: e.target.value }));
                    setPage(1);
                  }}
                  placeholder="SKU, nome ou observação..."
                />
              </div>
              <div className="form-field" style={{ minWidth: 185 }}>
                <label htmlFor="rep-mv-prod">Produto</label>
                <select
                  id="rep-mv-prod"
                  className="select"
                  value={movementFilters.product_id}
                  onChange={(e) => {
                    setMovementFilters((prev) => ({
                      ...prev,
                      product_id: e.target.value,
                    }));
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
              <div className="form-field" style={{ minWidth: 140 }}>
                <label htmlFor="rep-mv-type">Tipo</label>
                <select
                  id="rep-mv-type"
                  className="select"
                  value={movementFilters.movement_type}
                  onChange={(e) => {
                    setMovementFilters((prev) => ({
                      ...prev,
                      movement_type: e.target.value,
                    }));
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
              <div className="form-field" style={{ minWidth: 160 }}>
                <label htmlFor="rep-mv-user">Responsável</label>
                <select
                  id="rep-mv-user"
                  className="select"
                  value={movementFilters.user_id}
                  onChange={(e) => {
                    setMovementFilters((prev) => ({ ...prev, user_id: e.target.value }));
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
                <label htmlFor="rep-mv-start">De</label>
                <input
                  id="rep-mv-start"
                  type="date"
                  className="input"
                  value={movementFilters.start_date}
                  onChange={(e) => {
                    setMovementFilters((prev) => ({
                      ...prev,
                      start_date: e.target.value,
                    }));
                    setPage(1);
                  }}
                />
              </div>
              <div className="form-field">
                <label htmlFor="rep-mv-end">Até</label>
                <input
                  id="rep-mv-end"
                  type="date"
                  className="input"
                  value={movementFilters.end_date}
                  onChange={(e) => {
                    setMovementFilters((prev) => ({
                      ...prev,
                      end_date: e.target.value,
                    }));
                    setPage(1);
                  }}
                />
              </div>
            </>
          ) : null}

          {tab === "imported-history" ? (
            <>
              <div className="form-field" style={{ flex: "1 1 180px" }}>
                <label htmlFor="rep-imp-sku">SKU</label>
                <input
                  id="rep-imp-sku"
                  type="search"
                  className="input"
                  value={importedFilters.sku}
                  onChange={(e) => {
                    setImportedFilters((prev) => ({ ...prev, sku: e.target.value }));
                    setPage(1);
                  }}
                  placeholder="Ex: DEMO-001"
                />
              </div>
              <div className="form-field" style={{ minWidth: 130 }}>
                <label htmlFor="rep-imp-wh">Depósito</label>
                <input
                  id="rep-imp-wh"
                  type="text"
                  className="input"
                  value={importedFilters.warehouse}
                  onChange={(e) => {
                    setImportedFilters((prev) => ({
                      ...prev,
                      warehouse: e.target.value,
                    }));
                    setPage(1);
                  }}
                  placeholder="Ex: 1"
                />
              </div>
              <div className="form-field" style={{ minWidth: 155 }}>
                <label htmlFor="rep-imp-type">Evento</label>
                <select
                  id="rep-imp-type"
                  className="select"
                  value={importedFilters.event_type}
                  onChange={(e) => {
                    setImportedFilters((prev) => ({
                      ...prev,
                      event_type: e.target.value,
                    }));
                    setPage(1);
                  }}
                >
                  <option value="">Todos</option>
                  <option value="sale">Venda</option>
                  <option value="receipt">Recebimento</option>
                  <option value="return">Devolução</option>
                  <option value="other_outbound">Outra saída</option>
                </select>
              </div>
              <div className="form-field">
                <label htmlFor="rep-imp-start">De</label>
                <input
                  id="rep-imp-start"
                  type="date"
                  className="input"
                  value={importedFilters.start_date}
                  onChange={(e) => {
                    setImportedFilters((prev) => ({
                      ...prev,
                      start_date: e.target.value,
                    }));
                    setPage(1);
                  }}
                />
              </div>
              <div className="form-field">
                <label htmlFor="rep-imp-end">Até</label>
                <input
                  id="rep-imp-end"
                  type="date"
                  className="input"
                  value={importedFilters.end_date}
                  onChange={(e) => {
                    setImportedFilters((prev) => ({
                      ...prev,
                      end_date: e.target.value,
                    }));
                    setPage(1);
                  }}
                />
              </div>
            </>
          ) : null}

          {tab === "replenishment" ? (
            <>
              <div className="form-field" style={{ flex: "1 1 200px" }}>
                <label htmlFor="rep-repl-sku">SKU</label>
                <input
                  id="rep-repl-sku"
                  type="search"
                  className="input"
                  value={replenishmentFilters.sku}
                  onChange={(e) => {
                    setReplenishmentFilters((prev) => ({
                      ...prev,
                      sku: e.target.value,
                    }));
                    setPage(1);
                  }}
                  placeholder="Filtrar por SKU..."
                />
              </div>
              <div className="form-field" style={{ minWidth: 150 }}>
                <label htmlFor="rep-repl-wh">Depósito</label>
                <input
                  id="rep-repl-wh"
                  type="text"
                  className="input"
                  value={replenishmentFilters.warehouse}
                  onChange={(e) => {
                    setReplenishmentFilters((prev) => ({
                      ...prev,
                      warehouse: e.target.value,
                    }));
                    setPage(1);
                  }}
                  placeholder="Ex: 1"
                />
              </div>
            </>
          ) : null}

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleResetActiveFilters}
          >
            <RotateCcw size={14} aria-hidden="true" />
            <span>Limpar filtros</span>
          </button>
        </div>

        {loading ? (
          <div className="state-box">Carregando dados do relatório...</div>
        ) : tab === "current-stock" || tab === "below-minimum" ? (
          stockRows.length === 0 ? (
            <div className="state-box">
              Nenhum produto encontrado para este relatório.
            </div>
          ) : (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Produto</th>
                      <th>Categoria</th>
                      <th className="td-numeric">Saldo Atual</th>
                      <th className="td-numeric">Mínimo</th>
                      <th className="td-numeric">Custo Ref.</th>
                      <th className="td-numeric">Valor Estimado (Ref.)</th>
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
                        <td className="td-numeric">
                          <strong>
                            {formatQuantity(p.current_stock, p.unit)} {p.unit}
                          </strong>
                        </td>
                        <td className="td-numeric">
                          {formatQuantity(p.min_stock, p.unit)} {p.unit}
                        </td>
                        <td className="td-numeric">{formatCurrencyBRL(p.unit_cost)}</td>
                        <td className="td-numeric">
                          {formatCurrencyBRL(p.estimated_total_value)}
                        </td>
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
        ) : tab === "movements" ? (
          movementRows.length === 0 ? (
            <div className="state-box">
              Nenhuma movimentação encontrada para este relatório.
            </div>
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
                      <th className="td-numeric">Quantidade</th>
                      <th className="td-numeric">Saldo Final</th>
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
                        <td className="td-numeric">
                          {Number(m.signed_quantity) > 0 ? "+" : "-"}
                          {formatQuantity(m.quantity, m.unit_snapshot)} {m.unit_snapshot}
                        </td>
                        <td className="td-numeric">
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
          )
        ) : tab === "imported-history" ? (
          !importedReport || importedReport.items.length === 0 ? (
            <div className="state-box">
              <h3>Histórico importado sem registros no recorte</h3>
              <p>
                {importedReport?.status_message ||
                  "Nenhum registro de histórico importado encontrado para os filtros informados."}
              </p>
            </div>
          ) : (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Data do evento</th>
                      <th>SKU / Produto</th>
                      <th>Depósito</th>
                      <th>Evento</th>
                      <th className="td-numeric">Quantidade</th>
                      <th className="td-numeric">Custo Unit.</th>
                      <th>Disponibilidade</th>
                      <th>Lote / Data fonte</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importedReport.items.map((row) => (
                      <tr key={row.record_id}>
                        <td>{formatDateBR(row.event_date)}</td>
                        <td>
                          <span className="mono">{row.sku}</span> — {row.product_name}
                        </td>
                        <td className="mono">{row.warehouse}</td>
                        <td>{translateImportedEventType(row.event_type)}</td>
                        <td className="td-numeric">
                          {formatQuantity(row.quantity, row.unit)} {row.unit}
                        </td>
                        <td className="td-numeric">
                          {row.unit_cost !== null
                            ? formatCurrencyBRL(row.unit_cost)
                            : "—"}
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              row.stock_availability === "stockout"
                                ? "badge-danger"
                                : row.stock_availability === "available"
                                ? "badge-success"
                                : "badge-neutral"
                            }`}
                          >
                            {translateCoverageStatus(row.stock_availability)}
                          </span>
                        </td>
                        <td>
                          <span className="mono">{row.batch_id}</span>
                          {row.source_date ? ` · ${formatDateBR(row.source_date)}` : ""}
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
        ) : !replenishmentReport || replenishmentReport.items.length === 0 ? (
          <div className="state-box">
            <h3>
              {replenishmentReport?.status === "calculating"
                ? "Atualizando dados"
                : replenishmentReport?.status === "insufficient_data"
                ? "Dados insuficientes"
                : "Nenhuma sugestão disponível"}
            </h3>
            <p>
              {replenishmentReport?.status_message ||
                "Nenhuma sugestão de reposição armazenada para os filtros informados."}
            </p>
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>SKU / Produto</th>
                    <th>Depósito</th>
                    <th className="td-numeric">Quantidade sugerida</th>
                    <th>Data de referência</th>
                    <th>Origem</th>
                  </tr>
                </thead>
                <tbody>
                  {replenishmentReport.items.map((row) => (
                    <tr key={`${row.model_run_id}-${row.sku}-${row.warehouse}`}>
                      <td>
                        <div className="mono">{row.sku}</div>
                        <strong>{row.product_name}</strong>
                      </td>
                      <td className="mono">{row.warehouse}</td>
                      <td className="td-numeric">
                        <strong>
                          {formatQuantity(row.recommended_quantity, row.unit)} {row.unit}
                        </strong>
                      </td>
                      <td>{formatDateBR(row.reference_date)}</td>
                      <td>
                        {row.source === "synthetic"
                          ? "Simulação acadêmica"
                          : "Histórico legado calibrado"}
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
      </section>
    </div>
  );
}
