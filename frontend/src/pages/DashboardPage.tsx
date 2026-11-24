import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  PackageX,
  RefreshCw,
} from "lucide-react";
import { MovementModal, type MovementModalMode } from "../components/MovementModal";
import { useAuth } from "../context/AuthContext";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type {
  DashboardData,
  PaginatedResponse,
  Product,
  Supplier,
} from "../types/api";
import {
  formatCurrencyBRL,
  formatDateBR,
  formatQuantity,
} from "../utils/format";

const ATTENTION_LIMIT = 20;

export function DashboardPage() {
  const { isAdmin } = useAuth();

  const [days, setDays] = useState<string>("30");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [selectedChartUnit, setSelectedChartUnit] = useState<string>("ALL");

  const [data, setData] = useState<DashboardData | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<MovementModalMode>("ENTRADA");
  const [modalProductId, setModalProductId] = useState<number | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs =
        days === "custom" && startDate && endDate
          ? buildQueryString({ start_date: startDate, end_date: endDate })
          : buildQueryString({ days: days === "custom" ? 30 : Number(days) });

      const [dashRes, prodRes, supRes] = await Promise.all([
        apiRequest<DashboardData>(`/dashboard${qs}`),
        apiRequest<PaginatedResponse<Product>>("/products?is_active=true&page_size=200"),
        apiRequest<PaginatedResponse<Supplier>>("/suppliers?is_active=true&page_size=200"),
      ]);
      setData(dashRes);
      setProducts(prodRes.items);
      setSuppliers(supRes.items);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Erro ao carregar indicadores do painel."
      );
    } finally {
      setLoading(false);
    }
  }, [days, startDate, endDate]);

  useEffect(() => {
    if (days !== "custom" || (startDate && endDate)) {
      loadDashboard();
    }
  }, [loadDashboard, days, startDate, endDate]);

  useEffect(() => {
    if (
      selectedChartUnit !== "ALL" &&
      data &&
      !data.unit_summaries.some((u) => u.unit === selectedChartUnit)
    ) {
      setSelectedChartUnit("ALL");
    }
  }, [data, selectedChartUnit]);

  const openQuickMovement = (mode: MovementModalMode, productId?: number) => {
    setModalMode(mode);
    setModalProductId(productId ?? null);
    setModalOpen(true);
  };

  const chartPoints = data?.daily_chart || [];
  const visibleChartPoints =
    chartPoints.length > 31 ? chartPoints.slice(chartPoints.length - 31) : chartPoints;

  const selectedUnitMeta = data?.unit_summaries.find(
    (u) => u.unit === selectedChartUnit
  );

  const chartUnitLabel =
    selectedChartUnit === "ALL"
      ? "lançamentos/dia"
      : `${selectedChartUnit}${selectedUnitMeta ? ` (${selectedUnitMeta.unit_label})` : ""}`;

  const getChartValues = (point: DashboardData["daily_chart"][number]) => {
    if (selectedChartUnit === "ALL") {
      return { inVal: point.entries_count, outVal: point.exits_count };
    }
    const unitData = point.by_unit[selectedChartUnit];
    return {
      inVal: unitData ? Number(unitData.entries_qty) : 0,
      outVal: unitData ? Number(unitData.exits_qty) : 0,
    };
  };

  const rawMaxChartValue = visibleChartPoints.reduce((acc, pt) => {
    const { inVal, outVal } = getChartValues(pt);
    return Math.max(acc, inVal, outVal);
  }, 0);
  const maxChartValue = Math.max(1, rawMaxChartValue);

  const periodRangeLabel = data
    ? `${formatDateBR(data.period_start)} a ${formatDateBR(data.period_end)}`
    : "—";
  const referenceDateLabel = data ? formatDateBR(data.period_end) : "—";
  const attentionItems = data?.replenishment_list ?? [];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Painel de Estoque</h1>
          {data ? (
            <p className="page-subtitle tabular-nums" data-testid="dashboard-reference-date">
              Data de referência: <strong>{referenceDateLabel}</strong> · Período:{" "}
              <strong>{periodRangeLabel}</strong>
            </p>
          ) : null}
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => openQuickMovement("ENTRADA")}
          >
            <ArrowDownLeft size={16} aria-hidden="true" />
            <span>Registrar entrada</span>
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => openQuickMovement("SAIDA")}
          >
            <ArrowUpRight size={16} aria-hidden="true" />
            <span>Registrar saída</span>
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-icon"
            onClick={loadDashboard}
            disabled={loading}
            aria-label="Atualizar indicadores"
            title="Atualizar indicadores"
          >
            <RefreshCw size={16} aria-hidden="true" />
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

      {loading && !data ? (
        <div className="card state-box">Carregando indicadores do painel...</div>
      ) : data ? (
        <>
          {/* 1. What needs attention now */}
          <section className="card attention-panel" aria-labelledby="attention-title">
            <div className="panel-head">
              <div>
                <h2 id="attention-title" className="attention-title">
                  <span className="attention-marker" aria-hidden="true" />
                  Precisa de atenção
                </h2>
                <ul className="count-list" aria-label="Resumo de itens críticos">
                  <li className="count-chip danger">
                    <PackageX size={15} aria-hidden="true" />
                    <strong>{data.out_of_stock_count}</strong> sem estoque
                  </li>
                  <li className="count-chip warning">
                    <AlertCircle size={15} aria-hidden="true" />
                    <strong>{data.below_min_stock_count}</strong> abaixo do mínimo
                  </li>
                </ul>
              </div>
              <Link
                to={isAdmin ? "/relatorios?tab=replenishment" : "/produtos"}
                className="btn btn-primary"
              >
                <span>{isAdmin ? "Ver reposição sugerida" : "Consultar saldos"}</span>
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
            </div>

            {attentionItems.length === 0 ? (
              <div className="state-box">
                <h3>Nenhum item abaixo do mínimo</h3>
                <p>Todos os produtos ativos estão com saldo igual ou superior ao mínimo configurado.</p>
              </div>
            ) : (
              <>
                {attentionItems.length > ATTENTION_LIMIT ? (
                  <p className="page-subtitle" style={{ marginBottom: 12 }}>
                    Exibindo <strong>{ATTENTION_LIMIT}</strong> de{" "}
                    <strong>{attentionItems.length}</strong> itens, em ordem de prioridade.
                  </p>
                ) : null}
                <div className="table-scroll-hint" aria-hidden="true">
                  Deslize horizontalmente para ver todas as colunas.
                </div>
                <div
                  className="table-wrap"
                  role="region"
                  aria-label="Itens que precisam de reposição"
                  tabIndex={0}
                >
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Produto</th>
                        <th>Situação</th>
                        <th className="td-numeric">Saldo atual</th>
                        <th className="td-numeric">Mínimo</th>
                        <th className="td-numeric">Faltam</th>
                        <th>Fornecedor / prazo</th>
                        <th>
                          <span className="sr-only">Ação</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {attentionItems.slice(0, ATTENTION_LIMIT).map((item) => {
                        const isOut = item.stock_status === "OUT_OF_STOCK";
                        return (
                          <tr key={item.product_id}>
                            <td>
                              <strong>{item.name}</strong>
                              <div className="cell-subtext">
                                <span className="mono">{item.sku}</span> · {item.category_name}
                              </div>
                            </td>
                            <td>
                              <span className={`status-text ${isOut ? "danger" : "warning"}`}>
                                {isOut ? (
                                  <PackageX size={15} aria-hidden="true" />
                                ) : (
                                  <AlertCircle size={15} aria-hidden="true" />
                                )}
                                {isOut ? "Sem estoque" : "Abaixo do mínimo"}
                              </span>
                            </td>
                            <td className="td-numeric">
                              <strong>
                                {formatQuantity(item.current_stock, item.unit)} {item.unit}
                              </strong>
                            </td>
                            <td className="td-numeric">
                              {formatQuantity(item.min_stock, item.unit)} {item.unit}
                            </td>
                            <td className="td-numeric">
                              {formatQuantity(item.deficit, item.unit)} {item.unit}
                            </td>
                            <td>
                              {item.preferred_supplier_name || "Não definido"}
                              {item.lead_time_days !== null ? ` · ${item.lead_time_days} d` : ""}
                            </td>
                            <td>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => openQuickMovement("ENTRADA", item.product_id)}
                                aria-label={`Registrar entrada de ${item.name}`}
                              >
                                <ArrowDownLeft size={14} aria-hidden="true" />
                                <span>Registrar entrada</span>
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>

          {/* 2. Period summary and trend */}
          <section className="card" aria-labelledby="period-title">
            <div className="panel-head">
              <div>
                <h2 id="period-title">Resumo do período</h2>
                <p className="page-subtitle">Calculado a partir das movimentações registradas no depósito.</p>
              </div>
              <div className="panel-controls">
                <div className="form-field" style={{ minWidth: 190 }}>
                  <label htmlFor="dash-period">Período</label>
                  <select
                    id="dash-period"
                    className="select"
                    value={days}
                    onChange={(e) => setDays(e.target.value)}
                  >
                    <option value="7">Últimos 7 dias</option>
                    <option value="30">Últimos 30 dias</option>
                    <option value="90">Últimos 90 dias</option>
                    <option value="custom">Período personalizado</option>
                  </select>
                </div>
                {days === "custom" ? (
                  <>
                    <div className="form-field">
                      <label htmlFor="dash-start">Data inicial</label>
                      <input
                        id="dash-start"
                        type="date"
                        className="input"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                      />
                    </div>
                    <div className="form-field">
                      <label htmlFor="dash-end">Data final</label>
                      <input
                        id="dash-end"
                        type="date"
                        className="input"
                        value={endDate}
                        onChange={(e) => setEndDate(e.target.value)}
                      />
                    </div>
                  </>
                ) : null}
                <div className="form-field" style={{ minWidth: 230 }}>
                  <label htmlFor="chart-unit-select">Unidade do gráfico</label>
                  <select
                    id="chart-unit-select"
                    className="select"
                    value={selectedChartUnit}
                    onChange={(e) => setSelectedChartUnit(e.target.value)}
                  >
                    <option value="ALL">Todas (lançamentos/dia)</option>
                    {data.unit_summaries.map((u) => (
                      <option key={u.unit} value={u.unit}>
                        Quantidade em {u.unit} ({u.unit_label})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <dl className="stat-row">
              <div>
                <dt>Entradas</dt>
                <dd>{data.entries_count}</dd>
              </div>
              <div>
                <dt>Saídas</dt>
                <dd>{data.exits_count}</dd>
              </div>
              <div>
                <dt>Ajustes e estornos</dt>
                <dd>
                  {data.adjustments_count} · {data.reversals_count}
                </dd>
              </div>
              <div>
                <dt>Produtos ativos</dt>
                <dd>{data.active_products_count}</dd>
              </div>
              <div>
                <dt>Valor estimado</dt>
                <dd>
                  {formatCurrencyBRL(data.estimated_stock_value_brl)}
                  <span className="stat-note">
                    {data.valuation_formula}. {data.valuation_disclaimer}
                  </span>
                </dd>
              </div>
            </dl>

            <div className="chart-meta-strip tabular-nums" data-testid="chart-meta-strip">
              <span className="chart-meta-item">
                Unidade: <strong>{chartUnitLabel}</strong>
              </span>
              <span className="chart-meta-item">
                Referência: <strong>{referenceDateLabel}</strong> ({periodRangeLabel})
              </span>
              <span className="chart-meta-item">
                Pico no período:{" "}
                <strong>
                  {selectedChartUnit === "ALL"
                    ? `${rawMaxChartValue} lanç.`
                    : `${formatQuantity(rawMaxChartValue, selectedChartUnit)} ${selectedChartUnit}`}
                </strong>
              </span>
            </div>

            {visibleChartPoints.length === 0 ? (
              <div className="state-box">
                <h3>Sem movimentações no período</h3>
                <p>Amplie o intervalo de datas para acompanhar a evolução diária.</p>
              </div>
            ) : (
              <>
                <div className="chart-container">
                  <div
                    className="chart-bars"
                    role="img"
                    aria-label={`Gráfico de entradas e saídas em ${chartUnitLabel} de ${periodRangeLabel}`}
                  >
                    {visibleChartPoints.map((pt) => {
                      const { inVal, outVal } = getChartValues(pt);
                      const inHeight = Math.round((inVal / maxChartValue) * 130);
                      const outHeight = Math.round((outVal / maxChartValue) * 130);
                      return (
                        <div
                          key={pt.date}
                          className="chart-day"
                          title={`${formatDateBR(pt.date)} — Entradas: ${inVal} ${chartUnitLabel} | Saídas: ${outVal} ${chartUnitLabel}`}
                        >
                          <div className="chart-pair">
                            <div
                              className="chart-bar entry"
                              style={{ height: `${inVal > 0 ? Math.max(4, inHeight) : 2}px` }}
                            />
                            <div
                              className="chart-bar exit"
                              style={{ height: `${outVal > 0 ? Math.max(4, outHeight) : 2}px` }}
                            />
                          </div>
                          <span className="chart-day-label">{pt.label}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
                <div className="chart-legend">
                  <span>
                    <span className="legend-dot" style={{ background: "var(--series-entry)" }} />
                    Entradas ({chartUnitLabel})
                  </span>
                  <span>
                    <span className="legend-dot" style={{ background: "var(--series-exit)" }} />
                    Saídas ({chartUnitLabel})
                  </span>
                  <Link
                    to={isAdmin ? "/relatorios?tab=movements" : "/movimentacoes"}
                    className="chart-legend-link"
                  >
                    <span>{isAdmin ? "Abrir relatório de movimentações" : "Abrir histórico"}</span>
                    <ArrowRight size={13} aria-hidden="true" />
                  </Link>
                </div>
              </>
            )}
          </section>

          {/* 3. Totals by unit */}
          <section className="card" aria-labelledby="units-title">
            <div className="panel-head">
              <h2 id="units-title">Totais por unidade de medida</h2>
              {isAdmin ? (
                <Link to="/relatorios?tab=current-stock" className="btn btn-secondary btn-sm">
                  <span>Relatório de estoque atual</span>
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              ) : null}
            </div>

            {data.unit_summaries.length === 0 ? (
              <div className="state-box">
                Nenhuma entrada ou saída registrada no período selecionado.
              </div>
            ) : (
              <div className="table-wrap" role="region" aria-label="Totais por unidade" tabIndex={0}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Unidade</th>
                      <th className="td-numeric">Entradas</th>
                      <th className="td-numeric">Saídas totais</th>
                      <th className="td-numeric">Saídas de demanda (venda/consumo)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.unit_summaries.map((u) => (
                      <tr key={u.unit}>
                        <td>
                          <strong>{u.unit}</strong>{" "}
                          <span style={{ color: "var(--ink-secondary)" }}>— {u.unit_label}</span>
                        </td>
                        <td className="td-numeric">
                          {formatQuantity(u.entries_qty, u.unit)} {u.unit}
                        </td>
                        <td className="td-numeric">
                          {formatQuantity(u.exits_qty, u.unit)} {u.unit}
                        </td>
                        <td className="td-numeric">
                          {formatQuantity(u.demand_exits_qty, u.unit)} {u.unit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}

      <MovementModal
        isOpen={modalOpen}
        mode={modalMode}
        products={products}
        suppliers={suppliers}
        initialProductId={modalProductId}
        onClose={() => setModalOpen(false)}
        onSuccess={(msg) => {
          setFeedback(msg);
          loadDashboard();
        }}
      />
    </div>
  );
}
