import { useCallback, useEffect, useState } from "react";
import { Download, RotateCcw } from "lucide-react";
import { Pagination } from "./Pagination";
import {
  apiRequest,
  ApiError,
  buildQueryString,
  downloadAuthenticatedFile,
} from "../services/api";
import type { ImportedHistoryRow, VersionedReport } from "../types/api";
import {
  formatCurrencyBRL,
  formatDateBR,
  formatQuantity,
} from "../utils/format";

export interface ImportedHistoryFilters {
  source: string;
  sku: string;
  warehouse: string;
  event_type: string;
  start_date: string;
  end_date: string;
}

const DEFAULT_FILTERS: ImportedHistoryFilters = {
  source: "",
  sku: "",
  warehouse: "",
  event_type: "",
  start_date: "",
  end_date: "",
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

function translateCoverageLabel(status: ImportedHistoryRow["stock_availability"]): string {
  switch (status) {
    case "available":
      return "Disponível";
    case "stockout":
      return "Ruptura confirmada";
    case "unknown":
      return "Desconhecida";
    case "uncovered":
      return "Sem cobertura";
  }
}

function translateSourceName(source: string): string {
  if (source === "firebird") return "Legado Firebird";
  return source;
}

interface ImportedHistoryTabPanelProps {
  initialSku?: string;
  initialWarehouse?: string;
  onExportFeedback?: (message: string | null) => void;
}

export function ImportedHistoryTabPanel({
  initialSku = "",
  initialWarehouse = "",
  onExportFeedback,
}: ImportedHistoryTabPanelProps) {
  const [filters, setFilters] = useState<ImportedHistoryFilters>({
    ...DEFAULT_FILTERS,
    sku: initialSku,
    warehouse: initialWarehouse,
  });
  const [page, setPage] = useState(1);
  const [report, setReport] =
    useState<VersionedReport<ImportedHistoryRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync deep-linked filters (e.g., from Exceptions -> Imported History)
  useEffect(() => {
    if (initialSku || initialWarehouse) {
      setFilters((prev) => ({
        ...prev,
        sku: initialSku || prev.sku,
        warehouse: initialWarehouse || prev.warehouse,
      }));
      setPage(1);
    }
  }, [initialSku, initialWarehouse]);

  const buildFilterParams = useCallback(
    () => ({
      source: filters.source || undefined,
      sku: filters.sku.trim() || undefined,
      warehouse: filters.warehouse.trim() || undefined,
      event_type: filters.event_type || undefined,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
    }),
    [filters]
  );

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({
        ...buildFilterParams(),
        page,
        page_size: 25,
      });
      const res = await apiRequest<VersionedReport<ImportedHistoryRow>>(
        `/reports/imported-history${qs}`
      );
      setReport(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Erro ao carregar histórico importado."
      );
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [buildFilterParams, page]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleExportCsv = async () => {
    setExporting(true);
    setError(null);
    onExportFeedback?.(null);
    try {
      const qs = buildQueryString({ ...buildFilterParams(), export: "csv" });
      await downloadAuthenticatedFile(
        `/reports/imported-history${qs}`,
        "relatorio_historico_importado.csv"
      );
      onExportFeedback?.("CSV do histórico importado exportado com os filtros ativos.");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Falha ao exportar CSV do histórico importado."
      );
    } finally {
      setExporting(false);
    }
  };

  const rows = report?.items ?? [];
  const firstRow = rows[0] ?? null;

  return (
    <div data-testid="imported-history-panel">
      <div className="panel-action-row">
        <div>
          <h2 className="panel-section-title">Histórico Importado (Base Legada)</h2>
          <p className="page-subtitle">
            Vendas, recebimentos, devoluções e outras saídas preservados com unidade, cobertura e data da fonte. Valores desconhecidos permanecem separados de zero.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={handleExportCsv}
          disabled={exporting}
          data-testid="imported-history-csv-btn"
        >
          <Download size={14} aria-hidden="true" />
          <span>{exporting ? "Exportando..." : "Exportar Histórico CSV"}</span>
        </button>
      </div>

      <div className="filters-bar">
        <div className="form-field" style={{ minWidth: 165 }}>
          <label htmlFor="rep-imp-source">Origem (fonte)</label>
          <select
            id="rep-imp-source"
            className="select"
            value={filters.source}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, source: e.target.value }));
              setPage(1);
            }}
          >
            <option value="">Todas as origens</option>
            <option value="firebird">Legado Firebird</option>
          </select>
        </div>
        <div className="form-field" style={{ flex: "1 1 170px" }}>
          <label htmlFor="rep-imp-sku">SKU</label>
          <input
            id="rep-imp-sku"
            type="search"
            className="input"
            value={filters.sku}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, sku: e.target.value }));
              setPage(1);
            }}
            placeholder="Ex: DEMO-001"
          />
        </div>
        <div className="form-field" style={{ minWidth: 120 }}>
          <label htmlFor="rep-imp-wh">Depósito</label>
          <input
            id="rep-imp-wh"
            type="text"
            className="input"
            value={filters.warehouse}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, warehouse: e.target.value }));
              setPage(1);
            }}
            placeholder="Ex: 1"
          />
        </div>
        <div className="form-field" style={{ minWidth: 155 }}>
          <label htmlFor="rep-imp-type">Tipo de evento</label>
          <select
            id="rep-imp-type"
            className="select"
            value={filters.event_type}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, event_type: e.target.value }));
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
            value={filters.start_date}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, start_date: e.target.value }));
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
            value={filters.end_date}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, end_date: e.target.value }));
              setPage(1);
            }}
          />
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => {
            setFilters(DEFAULT_FILTERS);
            setPage(1);
          }}
        >
          <RotateCcw size={14} aria-hidden="true" />
          <span>Limpar filtros</span>
        </button>
      </div>

      {error ? (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="state-box">Carregando histórico importado...</div>
      ) : rows.length === 0 ? (
        <div className="state-box" data-testid="imported-history-empty">
          <h3>
            {report?.status === "insufficient_data"
              ? "Dados insuficientes"
              : "Nenhum registro encontrado no histórico importado"}
          </h3>
          <p>
            {report?.status_message ||
              "Nenhum evento importado corresponde aos filtros atuais. Ausência de registros não equivale a demanda zero."}
          </p>
        </div>
      ) : (
        <>
          {firstRow ? (
            <div className="provenance-bar tabular-nums">
              <span>
                Origem: <strong>{translateSourceName(firstRow.source)}</strong>
              </span>
              <span>
                Lote: <strong className="mono">{firstRow.batch_id}</strong>
              </span>
              <span>
                Data do extrato fonte:{" "}
                <strong>
                  {firstRow.source_date ? formatDateBR(firstRow.source_date) : "Não informada"}
                </strong>
              </span>
            </div>
          ) : null}

          <div
            className="table-wrap"
            role="region"
            aria-label="Tabela de histórico importado"
            tabIndex={0}
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>Data do evento</th>
                  <th>SKU / Produto</th>
                  <th>Depósito</th>
                  <th>Evento</th>
                  <th className="td-numeric">Quantidade</th>
                  <th className="td-numeric">Custo Unit.</th>
                  <th>Cobertura / Disponibilidade</th>
                  <th>Origem / Lote</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.record_id}>
                    <td className="tabular-nums">{formatDateBR(row.event_date)}</td>
                    <td>
                      <div className="mono">{row.sku}</div>
                      <strong>{row.product_name}</strong>
                    </td>
                    <td className="mono">{row.warehouse}</td>
                    <td>
                      <span
                        className={`badge ${
                          row.event_type === "receipt"
                            ? "badge-success"
                            : row.event_type === "sale"
                            ? "badge-info"
                            : row.event_type === "return"
                            ? "badge-warning"
                            : "badge-neutral"
                        }`}
                      >
                        {translateImportedEventType(row.event_type)}
                      </span>
                    </td>
                    <td className="td-numeric">
                      <strong>
                        {formatQuantity(row.quantity, row.unit)} {row.unit}
                      </strong>
                    </td>
                    <td className="td-numeric">
                      {row.unit_cost !== null
                        ? formatCurrencyBRL(row.unit_cost)
                        : "Não informado"}
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          row.stock_availability === "stockout"
                            ? "badge-danger"
                            : row.stock_availability === "available"
                            ? "badge-success"
                            : row.stock_availability === "uncovered"
                            ? "badge-warning"
                            : "badge-neutral"
                        }`}
                      >
                        {translateCoverageLabel(row.stock_availability)}
                      </span>
                    </td>
                    <td>
                      <div>{translateSourceName(row.source)}</div>
                      <div className="cell-subtext mono">
                        {row.batch_id}
                        {row.source_date ? ` · ${formatDateBR(row.source_date)}` : ""}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="report-footnote">
            Valores marcados como &ldquo;Não informado&rdquo; ou &ldquo;Desconhecida&rdquo; representam ausência de dado na origem e não são convertidos em zero.
          </p>

          <Pagination
            page={report?.page ?? page}
            totalPages={report?.total_pages ?? 1}
            totalItems={report?.total ?? rows.length}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
