import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertOctagon,
  ArrowRight,
  CalendarOff,
  HelpCircle,
  RotateCcw,
} from "lucide-react";
import { Pagination } from "./Pagination";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type { InventoryExceptionRow, VersionedReport } from "../types/api";
import { formatDateBR } from "../utils/format";

interface ExceptionsFilters {
  sku: string;
  warehouse: string;
  coverage: string;
  start_date: string;
  end_date: string;
}

const DEFAULT_FILTERS: ExceptionsFilters = {
  sku: "",
  warehouse: "",
  coverage: "",
  start_date: "",
  end_date: "",
};

function getCoveragePresentation(coverage: InventoryExceptionRow["coverage"]) {
  switch (coverage) {
    case "stockout":
      return {
        label: "Ruptura confirmada",
        badgeClass: "badge-danger",
        icon: <AlertOctagon size={13} aria-hidden="true" />,
        guidance: "Ruptura com evidência na fonte — não confundir com lacuna de cobertura.",
      };
    case "unknown":
      return {
        label: "Disponibilidade desconhecida",
        badgeClass: "badge-neutral",
        icon: <HelpCircle size={13} aria-hidden="true" />,
        guidance: "Sem saldo confirmado nesta data; não assume ruptura nem demanda zero.",
      };
    case "uncovered":
      return {
        label: "Data sem cobertura",
        badgeClass: "badge-warning",
        icon: <CalendarOff size={13} aria-hidden="true" />,
        guidance: "Período fora da cobertura do extrato importado.",
      };
  }
}

export function InventoryExceptionsTabPanel() {
  const [filters, setFilters] = useState<ExceptionsFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [report, setReport] =
    useState<VersionedReport<InventoryExceptionRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadExceptions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({
        sku: filters.sku.trim() || undefined,
        warehouse: filters.warehouse.trim() || undefined,
        coverage: filters.coverage || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        page,
        page_size: 25,
      });
      const res = await apiRequest<VersionedReport<InventoryExceptionRow>>(
        `/reports/inventory-exceptions${qs}`
      );
      setReport(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Erro ao carregar exceções e lacunas de estoque."
      );
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    loadExceptions();
  }, [loadExceptions]);

  const rows = report?.items ?? [];

  return (
    <div data-testid="inventory-exceptions-panel">
      <div className="panel-action-row">
        <div>
          <h2 className="panel-section-title">Exceções de Estoque e Lacunas de Cobertura</h2>
          <p className="page-subtitle">
            Rupturas confirmadas, datas com disponibilidade desconhecida e lacunas de cobertura são mantidas separadas, sem alterar saldos ou inventar demanda.
          </p>
        </div>
      </div>

      <div className="filters-bar">
        <div className="form-field" style={{ flex: "1 1 170px" }}>
          <label htmlFor="rep-exc-sku">SKU</label>
          <input
            id="rep-exc-sku"
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
          <label htmlFor="rep-exc-wh">Depósito</label>
          <input
            id="rep-exc-wh"
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
        <div className="form-field" style={{ minWidth: 195 }}>
          <label htmlFor="rep-exc-cov">Tipo de cobertura / exceção</label>
          <select
            id="rep-exc-cov"
            className="select"
            value={filters.coverage}
            onChange={(e) => {
              setFilters((prev) => ({ ...prev, coverage: e.target.value }));
              setPage(1);
            }}
          >
            <option value="">Todas as exceções</option>
            <option value="stockout">Ruptura confirmada</option>
            <option value="unknown">Disponibilidade desconhecida</option>
            <option value="uncovered">Data sem cobertura</option>
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="rep-exc-start">De</label>
          <input
            id="rep-exc-start"
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
          <label htmlFor="rep-exc-end">Até</label>
          <input
            id="rep-exc-end"
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
        <div className="state-box">Carregando exceções e lacunas de cobertura...</div>
      ) : rows.length === 0 ? (
        <div className="state-box" data-testid="exceptions-empty-state">
          <h3>
            {report?.status === "insufficient_data"
              ? "Cobertura histórica ainda não importada"
              : "Nenhuma exceção ou lacuna registrada no recorte"}
          </h3>
          <p>
            {report?.status_message ||
              (filters.coverage === "stockout"
                ? "Nenhuma ruptura confirmada foi registrada neste intervalo. Isso reflete apenas datas com cobertura verificada."
                : "Nenhuma exceção ou lacuna de cobertura encontrada para os filtros aplicados.")}
          </p>
        </div>
      ) : (
        <>
          <div
            className="table-wrap"
            role="region"
            aria-label="Tabela de exceções e lacunas de cobertura"
            tabIndex={0}
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>Data de referência</th>
                  <th>SKU / Depósito</th>
                  <th>Classificação</th>
                  <th>Explicação da ocorrência</th>
                  <th>Origem / Lote</th>
                  <th>Histórico do SKU</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => {
                  const pres = getCoveragePresentation(row.coverage);
                  const historyHref = `/relatorios?tab=imported-history&sku=${encodeURIComponent(
                    row.sku
                  )}&warehouse=${encodeURIComponent(row.warehouse)}`;
                  return (
                    <tr
                      key={`${row.batch_id}-${row.sku}-${row.reference_date}-${row.coverage}-${idx}`}
                      data-coverage={row.coverage}
                    >
                      <td className="tabular-nums">
                        <strong>{formatDateBR(row.reference_date)}</strong>
                      </td>
                      <td>
                        <div className="mono">
                          <strong>{row.sku}</strong>
                        </div>
                        <div className="cell-subtext">Depósito {row.warehouse}</div>
                      </td>
                      <td>
                        <span className={`badge ${pres.badgeClass}`}>
                          {pres.icon}
                          <span>{pres.label}</span>
                        </span>
                      </td>
                      <td>
                        <div>{row.reason}</div>
                        <div className="cell-subtext">{pres.guidance}</div>
                      </td>
                      <td>
                        <div className="mono">{row.batch_id}</div>
                        <div className="cell-subtext tabular-nums">
                          Fonte: {row.source === "firebird" ? "Legado Firebird" : row.source}
                          {row.source_date ? ` · ${formatDateBR(row.source_date)}` : ""}
                        </div>
                      </td>
                      <td>
                        <Link
                          to={historyHref}
                          className="btn btn-secondary btn-sm"
                        >
                          <span>Ver histórico</span>
                          <ArrowRight size={13} aria-hidden="true" />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

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
