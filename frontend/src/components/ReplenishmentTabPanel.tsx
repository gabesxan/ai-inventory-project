import { useCallback, useEffect, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { Pagination } from "./Pagination";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type { ReplenishmentRow, VersionedReport } from "../types/api";
import {
  formatDateBR,
  formatDateTimeBR,
  formatQuantity,
} from "../utils/format";

const CALCULATING_POLL_MS = 4000;

interface ReplenishmentFilters {
  sku: string;
  warehouse: string;
}

const DEFAULT_FILTERS: ReplenishmentFilters = {
  sku: "",
  warehouse: "",
};

function formatModelOrigin(source: ReplenishmentRow["source"]): string {
  return source === "synthetic"
    ? "Simulação acadêmica"
    : "Histórico legado calibrado";
}

function getStatusHeadline(status: VersionedReport<ReplenishmentRow>["status"]): string {
  switch (status) {
    case "calculating":
      return "Atualizando dados";
    case "insufficient_data":
      return "Dados insuficientes";
    case "stale":
      return "Sugestão anterior exibida";
    case "empty":
      return "Nenhuma sugestão no recorte";
    case "ready":
      return "Sugestões disponíveis";
  }
}

export function ReplenishmentTabPanel() {
  const [filters, setFilters] = useState<ReplenishmentFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);

  const [report, setReport] = useState<VersionedReport<ReplenishmentRow> | null>(null);
  const [lastValidReport, setLastValidReport] =
    useState<VersionedReport<ReplenishmentRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const scopeKeyRef = useRef<string>("");
  const currentScopeKey = `${filters.sku.trim().toUpperCase()}|${filters.warehouse.trim()}|${page}`;

  const fetchReplenishment = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
      }
      setError(null);
      try {
        const qs = buildQueryString({
          sku: filters.sku.trim() || undefined,
          warehouse: filters.warehouse.trim() || undefined,
          page,
          page_size: 25,
        });
        const res = await apiRequest<VersionedReport<ReplenishmentRow>>(
          `/reports/replenishment${qs}`
        );
        setReport(res);
        if (res.items.length > 0 && (res.status === "ready" || res.status === "stale")) {
          setLastValidReport(res);
        } else if (res.status === "empty" || res.status === "insufficient_data") {
          setLastValidReport(null);
        }
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "Não foi possível carregar o relatório de reposição."
        );
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [filters.sku, filters.warehouse, page]
  );

  // Reset cached valid snapshot when user changes filter scope
  useEffect(() => {
    if (scopeKeyRef.current !== currentScopeKey) {
      scopeKeyRef.current = currentScopeKey;
      setLastValidReport(null);
    }
  }, [currentScopeKey]);

  // Automatic load on tab open / filter change — no manual AI launch button
  useEffect(() => {
    fetchReplenishment(false);
  }, [fetchReplenishment]);

  // Automatic quiet refresh while backend reports calculating
  useEffect(() => {
    if (report?.status !== "calculating") return;
    const timer = window.setInterval(() => {
      fetchReplenishment(true);
    }, CALCULATING_POLL_MS);
    return () => window.clearInterval(timer);
  }, [report?.status, fetchReplenishment]);

  const effectiveStatus = report?.status ?? null;
  const displayedReport =
    report && report.items.length > 0
      ? report
      : effectiveStatus === "calculating" && lastValidReport
      ? lastValidReport
      : report;

  const displayedItems = displayedReport?.items ?? [];
  const hasVisibleSuggestions = displayedItems.length > 0;
  const primaryRow = displayedItems[0] ?? null;

  return (
    <div className="replenishment-panel" data-testid="replenishment-panel">
      <div className="filters-bar">
        <div className="form-field" style={{ flex: "1 1 200px" }}>
          <label htmlFor="rep-repl-sku">SKU</label>
          <input
            id="rep-repl-sku"
            type="search"
            className="input"
            value={filters.sku}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, sku: e.target.value }));
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
            value={filters.warehouse}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, warehouse: e.target.value }));
              setPage(1);
            }}
            placeholder="Ex: 1"
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

      {!loading && effectiveStatus === "calculating" ? (
        <div className="alert alert-info" role="status" data-testid="replenishment-status-banner">
          <strong>Atualizando dados.</strong>{" "}
          {report?.status_message ||
            "Os cálculos de reposição estão sendo atualizados em segundo plano."}
          {hasVisibleSuggestions && primaryRow
            ? ` Exibindo a última sugestão válida de ${formatDateBR(primaryRow.reference_date)} enquanto a atualização conclui.`
            : " Esta visualização é atualizada automaticamente."}
        </div>
      ) : null}

      {!loading && effectiveStatus === "stale" && hasVisibleSuggestions ? (
        <div className="alert alert-warning" role="status" data-testid="replenishment-status-banner">
          <strong>Última sugestão válida mantida.</strong>{" "}
          {report?.status_message || "Esta sugestão precisa ser atualizada."}
          {primaryRow
            ? ` Referência original: ${formatDateBR(primaryRow.reference_date)} (gerada em ${formatDateTimeBR(primaryRow.generated_at)}).`
            : ""}
        </div>
      ) : null}

      {loading && !hasVisibleSuggestions ? (
        <div className="state-box">Carregando recomendações de reposição...</div>
      ) : !hasVisibleSuggestions ? (
        <div className="state-box" data-testid="replenishment-empty-state">
          <h3>{effectiveStatus ? getStatusHeadline(effectiveStatus) : "Nenhuma sugestão disponível"}</h3>
          <p>
            {report?.status_message ||
              (effectiveStatus === "insufficient_data"
                ? "Dados insuficientes para calcular uma recomendação neste recorte."
                : effectiveStatus === "calculating"
                ? "Atualizando dados em segundo plano. A tabela será preenchida automaticamente ao concluir."
                : "Nenhuma sugestão armazenada para os filtros informados.")}
          </p>
        </div>
      ) : (
        <>
          {primaryRow ? (
            <div className="provenance-bar tabular-nums" data-testid="replenishment-provenance">
              <span>
                Origem: <strong>{formatModelOrigin(primaryRow.source)}</strong>
              </span>
              <span>
                Referência: <strong>{formatDateBR(primaryRow.reference_date)}</strong>
              </span>
              <span>
                Gerada em: <strong>{formatDateTimeBR(primaryRow.generated_at)}</strong>
              </span>
              <span className="mono">
                {primaryRow.model_version} · {primaryRow.scenario}
              </span>
            </div>
          ) : null}

          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>SKU / Produto</th>
                  <th>Depósito</th>
                  <th className="td-numeric">Quantidade sugerida</th>
                  <th>Origem e atualização</th>
                  <th>Data de referência</th>
                </tr>
              </thead>
              <tbody>
                {displayedItems.map((row) => (
                  <tr key={`${row.model_run_id}-${row.sku}-${row.warehouse}`}>
                    <td>
                      <div className="mono">{row.sku}</div>
                      <strong>{row.product_name}</strong>
                    </td>
                    <td className="mono">{row.warehouse}</td>
                    <td className="td-numeric">
                      <div className="suggestion-qty-cell">
                        <strong>
                          {formatQuantity(row.recommended_quantity, row.unit)} {row.unit}
                        </strong>
                        <span className="ai-disclosure-text">
                          Sugestão gerada por IA
                        </span>
                      </div>
                    </td>
                    <td>
                      <div>{formatModelOrigin(row.source)}</div>
                      <div className="cell-subtext tabular-nums">
                        Atualizada em {formatDateTimeBR(row.generated_at)} ·{" "}
                        <span className="mono">{row.model_version}</span>
                      </div>
                    </td>
                    <td className="tabular-nums">
                      <div>{formatDateBR(row.reference_date)}</div>
                      <div className="cell-subtext mono">{row.scenario}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="report-footnote">
            As quantidades acima servem apenas como apoio à decisão de compra. Nenhum pedido é emitido automaticamente.
          </p>

          <Pagination
            page={displayedReport?.page ?? page}
            totalPages={displayedReport?.total_pages ?? 1}
            totalItems={displayedReport?.total ?? displayedItems.length}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
