import { useCallback, useEffect, useState } from "react";
import { Download, RotateCcw } from "lucide-react";
import { Pagination } from "./Pagination";
import {
  apiRequest,
  ApiError,
  buildQueryString,
  downloadAuthenticatedFile,
} from "../services/api";
import type { ImportQualityRow, VersionedReport } from "../types/api";
import { formatDateBR, formatDateTimeBR } from "../utils/format";

function translateRejectionReason(code: string): string {
  const map: Record<string, string> = {
    invalid_unit: "Unidade inválida",
    missing_sku: "SKU ausente",
    invalid_date: "Data inválida",
    negative_quantity: "Quantidade negativa",
    duplicate_record: "Registro duplicado",
    unknown_product: "Produto não mapeado",
  };
  return map[code] ?? code.replace(/_/g, " ");
}

export function LegacyImportQualityPanel() {
  const [warehouse, setWarehouse] = useState("");
  const [batchId, setBatchId] = useState("");
  const [page, setPage] = useState(1);

  const [report, setReport] = useState<VersionedReport<ImportQualityRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const buildParams = useCallback(
    () => ({
      warehouse: warehouse.trim() || undefined,
      batch_id: batchId.trim() || undefined,
    }),
    [warehouse, batchId]
  );

  const loadLegacyBatches = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({ ...buildParams(), page, page_size: 25 });
      const res = await apiRequest<VersionedReport<ImportQualityRow>>(
        `/ai/imports/legacy/batches${qs}`
      );
      setReport(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível consultar o status dos lotes legados."
      );
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [buildParams, page]);

  useEffect(() => {
    loadLegacyBatches();
  }, [loadLegacyBatches]);

  const handleExportCsv = async () => {
    setExporting(true);
    setError(null);
    setFeedback(null);
    try {
      const qs = buildQueryString({ ...buildParams(), export: "csv" });
      await downloadAuthenticatedFile(
        `/ai/imports/legacy/batches${qs}`,
        "qualidade_importacao_legada.csv"
      );
      setFeedback("CSV de qualidade de importação exportado.");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Falha ao exportar relatório de qualidade."
      );
    } finally {
      setExporting(false);
    }
  };

  const rows = report?.items ?? [];
  const latest = rows[0] ?? null;

  return (
    <section
      className="card"
      style={{ marginBottom: 16 }}
      aria-labelledby="legacy-import-quality-heading"
      data-testid="legacy-import-quality-panel"
    >
      <div className="panel-action-row">
        <div>
          <h2 id="legacy-import-quality-heading" className="panel-section-title">
            Status e Qualidade da Importação Legada
          </h2>
          <p className="page-subtitle">
            Resumo administrativo por lote importado da base legada, com motivos agregados de rejeição e cobertura diária (sem exposição de linhas brutas sensíveis).
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={handleExportCsv}
          disabled={exporting || loading}
        >
          <Download size={14} aria-hidden="true" />
          <span>{exporting ? "Exportando..." : "Exportar Qualidade CSV"}</span>
        </button>
      </div>

      <div className="filters-bar">
        <div className="form-field" style={{ minWidth: 150 }}>
          <label htmlFor="lq-warehouse">Depósito</label>
          <input
            id="lq-warehouse"
            type="text"
            className="input"
            value={warehouse}
            onChange={(e) => {
              setWarehouse(e.target.value);
              setPage(1);
            }}
            placeholder="Ex: 1"
          />
        </div>
        <div className="form-field" style={{ flex: "1 1 220px" }}>
          <label htmlFor="lq-batch">Identificador do lote</label>
          <input
            id="lq-batch"
            type="search"
            className="input"
            value={batchId}
            onChange={(e) => {
              setBatchId(e.target.value);
              setPage(1);
            }}
            placeholder="Ex: demo-batch-001"
          />
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => {
            setWarehouse("");
            setBatchId("");
            setPage(1);
          }}
        >
          <RotateCcw size={14} aria-hidden="true" />
          <span>Limpar filtros</span>
        </button>
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

      {loading ? (
        <div className="state-box">Carregando lotes de importação legada...</div>
      ) : rows.length === 0 ? (
        <div className="state-box" data-testid="legacy-quality-empty">
          <h3>Nenhum lote legado registrado neste recorte</h3>
          <p>
            {report?.status_message ||
              "Quando um extrato legado for importado, o resumo de cobertura e eventuais motivos de rejeição aparecerão aqui."}
          </p>
        </div>
      ) : (
        <>
          {latest ? (
            <div className="kpi-grid" data-testid="legacy-latest-summary">
              <div className="kpi-card primary">
                <div className="kpi-label">Último lote</div>
                <div className="kpi-value mono" style={{ fontSize: "1.15rem" }}>
                  {latest.batch_id}
                </div>
                <div className="kpi-helper">
                  Depósito {latest.warehouse} · Data fonte:{" "}
                  {latest.source_date ? formatDateBR(latest.source_date) : "Não informada"}
                </div>
              </div>
              <div className="kpi-card success">
                <div className="kpi-label">Linhas aceitas</div>
                <div className="kpi-value">{latest.accepted_rows}</div>
                <div className="kpi-helper">
                  Duplicadas ignoradas: {latest.duplicate_rows}
                </div>
              </div>
              <div className="kpi-card danger">
                <div className="kpi-label">Linhas rejeitadas</div>
                <div className="kpi-value">{latest.rejected_rows}</div>
                <div className="kpi-helper">
                  {Object.keys(latest.rejection_reasons).length > 0
                    ? `${Object.keys(latest.rejection_reasons).length} motivo(s) agregado(s)`
                    : "Sem rejeições registradas"}
                </div>
              </div>
              <div className="kpi-card warning">
                <div className="kpi-label">Cobertura (dias)</div>
                <div className="kpi-value" style={{ fontSize: "1.1rem" }}>
                  {latest.coverage
                    ? `${latest.coverage.available_days} disp. · ${latest.coverage.stockout_days} rupt.`
                    : "Não informada"}
                </div>
                <div className="kpi-helper">
                  {latest.coverage
                    ? `${latest.coverage.unknown_days} desc. · ${latest.coverage.uncovered_days} sem cobertura`
                    : "Sem detalhamento de cobertura"}
                </div>
              </div>
            </div>
          ) : null}

          <div
            className="table-wrap"
            role="region"
            aria-label="Tabela de lotes e qualidade da importação legada"
            tabIndex={0}
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>Lote / Depósito</th>
                  <th>Status / Data</th>
                  <th>Período coberto</th>
                  <th className="td-numeric">Aceitas / Rej. / Dup.</th>
                  <th>Motivos de rejeição (agregado)</th>
                  <th>Cobertura diária</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const reasons = Object.entries(row.rejection_reasons);
                  return (
                    <tr key={`${row.batch_id}-${row.warehouse}`}>
                      <td>
                        <div className="mono">
                          <strong>{row.batch_id}</strong>
                        </div>
                        <div className="cell-subtext">
                          Depósito {row.warehouse} · Fonte:{" "}
                          {row.source === "firebird" ? "Legado Firebird" : row.source}
                        </div>
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            row.status === "imported" ? "badge-success" : "badge-danger"
                          }`}
                        >
                          {row.status === "imported" ? "Importado" : "Falhou"}
                        </span>
                        <div className="cell-subtext tabular-nums">
                          {row.imported_at
                            ? formatDateTimeBR(row.imported_at)
                            : "Sem data de conclusão"}
                        </div>
                      </td>
                      <td className="tabular-nums">
                        <div>
                          {row.period_start && row.period_end
                            ? `${formatDateBR(row.period_start)} a ${formatDateBR(row.period_end)}`
                            : "Não informado"}
                        </div>
                        <div className="cell-subtext">
                          Extrato: {row.source_date ? formatDateBR(row.source_date) : "—"}
                        </div>
                      </td>
                      <td className="td-numeric">
                        <strong>{row.accepted_rows}</strong> / {row.rejected_rows} /{" "}
                        {row.duplicate_rows}
                      </td>
                      <td>
                        {reasons.length === 0 ? (
                          <span className="cell-subtext">Sem rejeições</span>
                        ) : (
                          <div className="reason-pill-list">
                            {reasons.map(([code, count]) => (
                              <span key={code} className="badge badge-warning">
                                {translateRejectionReason(code)} ({code}): {count}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="tabular-nums">
                        {row.coverage ? (
                          <div className="cell-subtext" style={{ color: "var(--ink-secondary)" }}>
                            Disp.: {row.coverage.available_days}d · Rupt.:{" "}
                            {row.coverage.stockout_days}d · Desc.: {row.coverage.unknown_days}d ·
                            Sem cob.: {row.coverage.uncovered_days}d
                          </div>
                        ) : (
                          "—"
                        )}
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
    </section>
  );
}
