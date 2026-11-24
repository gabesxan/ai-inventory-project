import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Download, RotateCcw } from "lucide-react";
import {
  apiRequest,
  ApiError,
  buildQueryString,
  downloadAuthenticatedFile,
} from "../services/api";
import type { ComparisonRow, ModelSource, VersionedReport } from "../types/api";
import {
  formatCurrencyBRL,
  formatDateBR,
  formatDateTimeBR,
} from "../utils/format";

const POLICY_ORDER: Array<ComparisonRow["policy"]> = ["base_stock", "s_s", "dqn"];

const numberFormatter2 = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const numberFormatter1 = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const percentFormatter = new Intl.NumberFormat("pt-BR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatPolicyLabel(policy: ComparisonRow["policy"]): string {
  switch (policy) {
    case "dqn":
      return "DQN";
    case "base_stock":
      return "Base-Stock";
    case "s_s":
      return "(s, S)";
  }
}

function formatSourceLabel(source: ModelSource): string {
  return source === "synthetic"
    ? "Simulação acadêmica"
    : "Histórico legado calibrado";
}

function parseNumeric(val: string | number | null): number | null {
  if (val === null || val === undefined || val === "") return null;
  const n = typeof val === "number" ? val : Number(val);
  return Number.isNaN(n) ? null : n;
}

function meanOf(values: Array<number | null>): number | null {
  const valid = values.filter((v): v is number => v !== null);
  if (valid.length === 0) return null;
  return valid.reduce((sum, v) => sum + v, 0) / valid.length;
}

interface ScenarioGroup {
  key: string;
  source: ModelSource;
  scenario: string;
  model_run_id: string;
  model_version: string;
  reference_date: string;
  trained_at: string;
  generated_at: string;
  rows: ComparisonRow[];
  seeds: number[];
}

interface PolicySummary {
  policy: ComparisonRow["policy"];
  count: number;
  meanCost: number | null;
  meanFillRate: number | null;
  meanStockoutDays: number | null;
  meanInventory: number | null;
  meanOrderDays: number | null;
}

export function PolicyComparisonSection() {
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [scenarioFilter, setScenarioFilter] = useState<string>("");
  const [runFilter, setRunFilter] = useState<string>("");

  const [report, setReport] = useState<VersionedReport<ComparisonRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportFeedback, setExportFeedback] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  const buildParams = useCallback(
    () => ({
      source: sourceFilter || undefined,
      scenario: scenarioFilter.trim() || undefined,
      model_run_id: runFilter.trim() || undefined,
    }),
    [sourceFilter, scenarioFilter, runFilter]
  );

  const loadComparison = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({ ...buildParams(), page: 1, page_size: 200 });
      const res = await apiRequest<VersionedReport<ComparisonRow>>(
        `/reports/comparison${qs}`
      );
      setReport(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível carregar a comparação entre políticas."
      );
      setReport(null);
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  useEffect(() => {
    loadComparison();
  }, [loadComparison]);

  const handleExportCsv = async () => {
    setExporting(true);
    setError(null);
    setExportFeedback(null);
    try {
      const qs = buildQueryString({ ...buildParams(), export: "csv" });
      await downloadAuthenticatedFile(
        `/reports/comparison${qs}`,
        "relatorio_comparacao_politicas.csv"
      );
      setExportFeedback(
        "CSV da comparação entre políticas exportado com os filtros e precisão originais."
      );
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Falha ao exportar CSV da comparação de políticas."
      );
    } finally {
      setExporting(false);
    }
  };

  const groups = useMemo<ScenarioGroup[]>(() => {
    const items = report?.items ?? [];
    const map = new Map<string, ScenarioGroup>();
    for (const row of items) {
      const key = `${row.source}::${row.scenario}::${row.model_run_id}`;
      let group = map.get(key);
      if (!group) {
        group = {
          key,
          source: row.source,
          scenario: row.scenario,
          model_run_id: row.model_run_id,
          model_version: row.model_version,
          reference_date: row.reference_date,
          trained_at: row.trained_at,
          generated_at: row.generated_at,
          rows: [],
          seeds: [],
        };
        map.set(key, group);
      }
      group.rows.push(row);
      if (!group.seeds.includes(row.seed)) {
        group.seeds.push(row.seed);
      }
    }
    const list = Array.from(map.values());
    // Separate legacy_calibrated and synthetic deterministically
    list.sort((a, b) => {
      if (a.source !== b.source) {
        return a.source === "legacy_calibrated" ? -1 : 1;
      }
      if (a.scenario !== b.scenario) return a.scenario.localeCompare(b.scenario);
      return a.model_run_id.localeCompare(b.model_run_id);
    });
    for (const g of list) {
      g.seeds.sort((a, b) => a - b);
    }
    return list;
  }, [report]);

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderPolicySummaries = (group: ScenarioGroup): PolicySummary[] => {
    return POLICY_ORDER.map((policy) => {
      const policyRows = group.rows.filter((r) => r.policy === policy);
      return {
        policy,
        count: policyRows.length,
        meanCost: meanOf(policyRows.map((r) => parseNumeric(r.total_cost))),
        meanFillRate: meanOf(policyRows.map((r) => parseNumeric(r.fill_rate))),
        meanStockoutDays: meanOf(policyRows.map((r) => parseNumeric(r.stockout_days))),
        meanInventory: meanOf(policyRows.map((r) => parseNumeric(r.mean_inventory))),
        meanOrderDays: meanOf(policyRows.map((r) => parseNumeric(r.order_days))),
      };
    });
  };

  return (
    <section
      className="comparison-section"
      aria-labelledby="policy-comparison-heading"
      data-testid="policy-comparison-section"
    >
      <div className="comparison-header">
        <div>
          <h2 id="policy-comparison-heading">Comparação de Políticas e Proveniência</h2>
          <p className="page-subtitle">
            Avaliação pareada entre DQN, Base-Stock e (s, S) por cenário e origem dos dados, exibindo resultados medidos sem omissões.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={handleExportCsv}
          disabled={exporting || loading}
        >
          <Download size={14} aria-hidden="true" />
          <span>{exporting ? "Exportando..." : "Exportar Comparação CSV"}</span>
        </button>
      </div>

      <div className="filters-bar">
        <div className="form-field" style={{ minWidth: 200 }}>
          <label htmlFor="cmp-source">Origem dos cenários</label>
          <select
            id="cmp-source"
            className="select"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            <option value="">Todas as origens</option>
            <option value="synthetic">Simulação acadêmica</option>
            <option value="legacy_calibrated">Histórico legado calibrado</option>
          </select>
        </div>
        <div className="form-field" style={{ flex: "1 1 180px" }}>
          <label htmlFor="cmp-scenario">Cenário</label>
          <input
            id="cmp-scenario"
            type="search"
            className="input"
            value={scenarioFilter}
            onChange={(e) => setScenarioFilter(e.target.value)}
            placeholder="Ex: demo-poisson"
          />
        </div>
        <div className="form-field" style={{ flex: "1 1 180px" }}>
          <label htmlFor="cmp-run">Execução (model_run_id)</label>
          <input
            id="cmp-run"
            type="search"
            className="input"
            value={runFilter}
            onChange={(e) => setRunFilter(e.target.value)}
            placeholder="Filtrar por ID da execução..."
          />
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => {
            setSourceFilter("");
            setScenarioFilter("");
            setRunFilter("");
          }}
        >
          <RotateCcw size={14} aria-hidden="true" />
          <span>Limpar</span>
        </button>
      </div>

      {exportFeedback ? (
        <div className="alert alert-success" role="status" data-testid="comparison-export-feedback">
          {exportFeedback}
        </div>
      ) : null}

      {error ? (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="state-box">Carregando comparação de políticas...</div>
      ) : groups.length === 0 ? (
        <div className="state-box" data-testid="comparison-empty-state">
          <h3>
            {report?.status === "calculating"
              ? "Atualizando dados"
              : report?.status === "insufficient_data"
              ? "Dados insuficientes"
              : "Nenhuma avaliação disponível"}
          </h3>
          <p>
            {report?.status_message ||
              "Nenhum resultado de comparação encontrado para o recorte selecionado."}
          </p>
        </div>
      ) : (
        <div className="comparison-groups">
          {groups.map((group) => {
            const summaries = renderPolicySummaries(group);
            const isExpanded = Boolean(expandedGroups[group.key]);
            const sortedDetailRows = [...group.rows].sort((a, b) => {
              if (a.seed !== b.seed) return a.seed - b.seed;
              return POLICY_ORDER.indexOf(a.policy) - POLICY_ORDER.indexOf(b.policy);
            });

            return (
              <div
                key={group.key}
                className="comparison-group-card"
                data-testid={`comparison-group-${group.source}`}
              >
                <div className="comparison-group-meta tabular-nums">
                  <div className="comparison-group-title">
                    <span
                      className={`badge ${
                        group.source === "legacy_calibrated"
                          ? "badge-info"
                          : "badge-neutral"
                      }`}
                    >
                      {formatSourceLabel(group.source)}
                    </span>
                    <strong className="mono">{group.scenario}</strong>
                    <span className="comparison-meta-sep">·</span>
                    <span>
                      {group.seeds.length} instância(s) pareada(s) ({group.rows.length} registros)
                    </span>
                  </div>
                  <div className="comparison-group-dates">
                    <span>
                      Referência: <strong>{formatDateBR(group.reference_date)}</strong>
                    </span>
                    <span className="mono">{group.model_version}</span>
                  </div>
                </div>

                <div
                  className="table-wrap"
                  role="region"
                  aria-label={`Resumo da comparação de políticas para ${group.scenario}`}
                  tabIndex={0}
                >
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Política</th>
                        <th className="td-numeric">Custo total médio (R$)</th>
                        <th className="td-numeric">Nível de serviço (%)</th>
                        <th className="td-numeric">Dias de ruptura (média)</th>
                        <th className="td-numeric">Estoque médio (un.)</th>
                        <th className="td-numeric">Dias com pedido (média)</th>
                        <th className="td-numeric">Seeds</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summaries.map((item) => (
                        <tr key={item.policy} data-policy={item.policy}>
                          <td>
                            <strong>{formatPolicyLabel(item.policy)}</strong>
                          </td>
                          <td className="td-numeric">
                            {item.meanCost !== null
                              ? formatCurrencyBRL(item.meanCost)
                              : "—"}
                          </td>
                          <td className="td-numeric">
                            {item.meanFillRate !== null
                              ? percentFormatter.format(item.meanFillRate)
                              : "—"}
                          </td>
                          <td className="td-numeric">
                            {item.meanStockoutDays !== null
                              ? `${numberFormatter1.format(item.meanStockoutDays)} d`
                              : "—"}
                          </td>
                          <td className="td-numeric">
                            {item.meanInventory !== null
                              ? `${numberFormatter2.format(item.meanInventory)} un.`
                              : "—"}
                          </td>
                          <td className="td-numeric">
                            {item.meanOrderDays !== null
                              ? `${numberFormatter1.format(item.meanOrderDays)} d`
                              : "—"}
                          </td>
                          <td className="td-numeric">{item.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="comparison-expand-bar">
                  <button
                    type="button"
                    className="btn btn-subtle btn-sm"
                    aria-expanded={isExpanded}
                    onClick={() => toggleGroup(group.key)}
                  >
                    {isExpanded ? (
                      <ChevronDown size={15} aria-hidden="true" />
                    ) : (
                      <ChevronRight size={15} aria-hidden="true" />
                    )}
                    <span>
                      {isExpanded
                        ? "Ocultar detalhes por seed e metadados"
                        : "Expandir detalhes por seed e metadados da execução"}
                    </span>
                  </button>
                </div>

                {isExpanded ? (
                  <div className="comparison-details-box" data-testid="comparison-expanded-details">
                    <div className="provenance-bar tabular-nums">
                      <span>
                        Origem: <strong>{formatSourceLabel(group.source)}</strong>
                      </span>
                      <span>
                        Execução: <strong className="mono">{group.model_run_id}</strong>
                      </span>
                      <span>
                        Treinado em: <strong>{formatDateTimeBR(group.trained_at)}</strong>
                      </span>
                      <span>
                        Gerado em: <strong>{formatDateTimeBR(group.generated_at)}</strong>
                      </span>
                    </div>

                    <div
                      className="table-wrap"
                      role="region"
                      aria-label={`Detalhes por seed para ${group.scenario}`}
                      tabIndex={0}
                    >
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th className="td-numeric">Seed</th>
                            <th>Política</th>
                            <th className="td-numeric">Custo total (R$)</th>
                            <th className="td-numeric">Nível de serviço (%)</th>
                            <th className="td-numeric">Rupturas (dias)</th>
                            <th className="td-numeric">Estoque médio (un.)</th>
                            <th className="td-numeric">Pedidos (dias)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sortedDetailRows.map((row) => {
                            const fill = parseNumeric(row.fill_rate);
                            const inv = parseNumeric(row.mean_inventory);
                            return (
                              <tr key={`${row.model_run_id}-${row.seed}-${row.policy}`}>
                                <td className="td-numeric mono">{row.seed}</td>
                                <td>{formatPolicyLabel(row.policy)}</td>
                                <td className="td-numeric">
                                  {row.total_cost !== null
                                    ? formatCurrencyBRL(row.total_cost)
                                    : "—"}
                                </td>
                                <td className="td-numeric">
                                  {fill !== null ? percentFormatter.format(fill) : "—"}
                                </td>
                                <td className="td-numeric">
                                  {row.stockout_days !== null
                                    ? `${row.stockout_days} d`
                                    : "—"}
                                </td>
                                <td className="td-numeric">
                                  {inv !== null
                                    ? `${numberFormatter2.format(inv)} un.`
                                    : "—"}
                                </td>
                                <td className="td-numeric">
                                  {row.order_days !== null ? `${row.order_days} d` : "—"}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
