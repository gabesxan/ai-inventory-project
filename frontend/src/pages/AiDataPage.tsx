import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Database,
  Download,
  FileSpreadsheet,
  Upload,
} from "lucide-react";
import { LegacyImportQualityPanel } from "../components/LegacyImportQualityPanel";
import {
  apiRequest,
  ApiError,
  buildQueryString,
  downloadAuthenticatedFile,
} from "../services/api";
import type {
  ImportBatchSummary,
  ImportConfirmOut,
  ImportPreviewOut,
} from "../types/api";
import { formatDateTimeBR, formatQuantity } from "../utils/format";

export function AiDataPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewOut | null>(null);
  const [batches, setBatches] = useState<ImportBatchSummary[]>([]);
  const [includeSynthetic, setIncludeSynthetic] = useState(true);
  const [includeHistorical, setIncludeHistorical] = useState(true);

  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadBatches = useCallback(async () => {
    try {
      const res = await apiRequest<ImportBatchSummary[]>("/ai/imports/batches");
      setBatches(res);
    } catch {
      // ignora erro secundário
    }
  }, []);

  useEffect(() => {
    loadBatches();
  }, [loadBatches]);

  const handlePreviewUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setError("Selecione um arquivo CSV para gerar a prévia.");
      return;
    }
    setUploading(true);
    setError(null);
    setFeedback(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const res = await apiRequest<ImportPreviewOut>("/ai/imports/preview", {
        method: "POST",
        body: formData,
      });
      setPreview(res);
      await loadBatches();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro ao processar prévia do CSV."
      );
    } finally {
      setUploading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!preview) return;
    setConfirming(true);
    setError(null);
    try {
      const res = await apiRequest<ImportConfirmOut>(
        `/ai/imports/${preview.batch_id}/confirm`,
        { method: "POST" }
      );
      setFeedback(
        `${res.notice} (${res.inserted_rows} registro(s) inserido(s) na base histórica.)`
      );
      setPreview(null);
      setSelectedFile(null);
      await loadBatches();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível confirmar a importação."
      );
    } finally {
      setConfirming(false);
    }
  };

  const handleDownload = async (path: string, filename: string, key: string) => {
    setDownloading(key);
    setError(null);
    try {
      await downloadAuthenticatedFile(path, filename);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falha no download.");
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Importação e Dados Históricos</h1>
          <p className="page-subtitle">
            Acompanhe a qualidade de extratos legados, importe histórico por CSV (sem alterar saldos reais) e exporte bases tratadas.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() =>
              handleDownload(
                "/ai/imports/template",
                "modelo_importacao_historico.csv",
                "template"
              )
            }
            disabled={downloading === "template"}
          >
            <Download size={16} />
            <span>Baixar Modelo CSV</span>
          </button>
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

      <LegacyImportQualityPanel />

      <div className="split-grid" style={{ marginBottom: 18 }}>
        <div className="card">
          <div className="card-title-row">
            <h2>1. Importar Histórico CSV (Estudo / Análise)</h2>
          </div>
          <div className="alert alert-info">
            <div>
              <strong>Integridade garantida:</strong> importações nesta tela alimentam
              apenas a base histórica analítica para o projeto de IA e{" "}
              <strong>não alteram o saldo atual</strong> de nenhum produto.
            </div>
          </div>

          <form onSubmit={handlePreviewUpload}>
            <div className="form-field" style={{ marginBottom: 14 }}>
              <label htmlFor="csv-upload-input">Arquivo CSV (separado por vírgula ou ponto e vírgula)</label>
              <input
                id="csv-upload-input"
                type="file"
                accept=".csv,text/csv"
                className="input"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={uploading || !selectedFile}
            >
              <Upload size={16} />
              <span>{uploading ? "Validando arquivo..." : "Gerar Prévia e Validar"}</span>
            </button>
          </form>
        </div>

        <div className="card">
          <div className="card-title-row">
            <h2>2. Exportar Datasets para Python (pandas / scikit-learn)</h2>
          </div>
          <p className="page-subtitle" style={{ marginBottom: 14 }}>
            Exporte a série diária por produto (com separação entre demanda observada,
            dias em ruptura e dias sem informação) ou todas as movimentações analíticas.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={includeHistorical}
                onChange={(e) => setIncludeHistorical(e.target.checked)}
              />
              <span>Incluir registros históricos importados (estudo)</span>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={includeSynthetic}
                onChange={(e) => setIncludeSynthetic(e.target.checked)}
              />
              <span>Incluir registros sinalizados como sintéticos (demonstração)</span>
            </label>
          </div>

          <div className="header-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() =>
                handleDownload(
                  `/ai/exports/daily-series${buildQueryString({
                    include_historical: includeHistorical,
                    include_synthetic: includeSynthetic,
                  })}`,
                  "serie_diaria_ia_produtos.csv",
                  "daily"
                )
              }
              disabled={downloading === "daily"}
            >
              <Database size={16} />
              <span>
                {downloading === "daily"
                  ? "Gerando CSV..."
                  : "Exportar Série Diária por Produto (CSV)"}
              </span>
            </button>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() =>
                handleDownload(
                  `/ai/exports/movements${buildQueryString({
                    include_historical: includeHistorical,
                    include_synthetic: includeSynthetic,
                  })}`,
                  "movimentacoes_analiticas_ia.csv",
                  "movements"
                )
              }
              disabled={downloading === "movements"}
            >
              <FileSpreadsheet size={16} />
              <span>Exportar Movimentações Analíticas (CSV)</span>
            </button>
          </div>
        </div>
      </div>

      {preview ? (
        <div className="card" style={{ marginBottom: 18 }}>
          <div className="card-title-row">
            <div>
              <h2>Prévia da Importação: {preview.filename}</h2>
              <p className="page-subtitle">{preview.notice}</p>
            </div>
            <button
              type="button"
              className="btn btn-success"
              disabled={confirming || preview.valid_rows === 0}
              onClick={handleConfirmImport}
            >
              <CheckCircle2 size={16} />
              <span>
                {confirming
                  ? "Confirmando..."
                  : `Confirmar Gravação (${preview.valid_rows} válida(s))`}
              </span>
            </button>
          </div>

          {preview.file_already_imported ? (
            <div className="alert alert-warning">
              Este exato arquivo (mesmo SHA-256) já foi importado anteriormente. Linhas
              já existentes foram marcadas como duplicadas.
            </div>
          ) : null}

          <div className="kpi-grid">
            <div className="kpi-card primary">
              <div className="kpi-label">Linhas Lidas</div>
              <div className="kpi-value">{preview.total_rows}</div>
            </div>
            <div className="kpi-card success">
              <div className="kpi-label">Linhas Válidas</div>
              <div className="kpi-value">{preview.valid_rows}</div>
            </div>
            <div className="kpi-card danger">
              <div className="kpi-label">Erros / Rejeitadas</div>
              <div className="kpi-value">{preview.error_rows}</div>
            </div>
            <div className="kpi-card warning">
              <div className="kpi-label">Duplicadas Bloqueadas</div>
              <div className="kpi-value">{preview.duplicate_rows}</div>
            </div>
          </div>

          {preview.errors.length > 0 ? (
            <div style={{ marginBottom: 16 }}>
              <h3>Relatório de Erros por Linha</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Linha</th>
                      <th>SKU</th>
                      <th>Motivo da Rejeição</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.errors.map((err, idx) => (
                      <tr key={`${err.line_number}-${idx}`}>
                        <td>Linha {err.line_number}</td>
                        <td className="mono">{err.sku || "—"}</td>
                        <td style={{ color: "#b91c1c" }}>{err.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}

          {preview.sample_valid_rows.length > 0 ? (
            <div>
              <h3>Amostra das Linhas Válidas (até 20 primeiras)</h3>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Linha</th>
                      <th>Data/Hora</th>
                      <th>SKU / Produto</th>
                      <th>Tipo / Motivo</th>
                      <th>Quantidade</th>
                      <th>Demanda?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample_valid_rows.map((row) => (
                      <tr key={row.line_number}>
                        <td>{row.line_number}</td>
                        <td>{formatDateTimeBR(row.occurred_at)}</td>
                        <td>
                          <span className="mono">{row.sku}</span> — {row.product_name}
                        </td>
                        <td>
                          {row.movement_type} / {row.reason_code}
                        </td>
                        <td>
                          {formatQuantity(row.quantity, row.unit_snapshot)}{" "}
                          {row.unit_snapshot}
                        </td>
                        <td>{row.is_demand ? "Sim" : "Não"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="card">
        <div className="card-title-row">
          <h2>Histórico de Lotes de Importação</h2>
        </div>
        {batches.length === 0 ? (
          <div className="state-box">Nenhuma importação histórica realizada até o momento.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Lote</th>
                  <th>Arquivo</th>
                  <th>Status</th>
                  <th>Válidas / Erros / Duplicadas</th>
                  <th>Origem</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.id}>
                    <td className="mono">#{b.id}</td>
                    <td>{b.filename}</td>
                    <td>
                      <span
                        className={`badge ${
                          b.status === "CONFIRMED" ? "badge-success" : "badge-warning"
                        }`}
                      >
                        {b.status === "CONFIRMED" ? "Confirmado" : "Prévia"}
                      </span>
                    </td>
                    <td>
                      {b.valid_rows} vál. / {b.error_rows} err. / {b.duplicate_rows} dup.
                    </td>
                    <td>
                      {b.is_synthetic ? (
                        <span className="badge badge-warning">Sintético</span>
                      ) : (
                        <span className="badge badge-info">Real</span>
                      )}
                    </td>
                    <td>{formatDateTimeBR(b.confirmed_at || b.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
