import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  Calendar,
  DollarSign,
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

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Painel de Estoque</h1>
          <p className="page-subtitle">
            Indicadores operacionais calculados a partir das movimentações registradas no depósito.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-success"
            onClick={() => openQuickMovement("ENTRADA")}
          >
            <ArrowDownLeft size={16} aria-hidden="true" />
            <span>Registrar Entrada</span>
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => openQuickMovement("SAIDA")}
          >
            <ArrowUpRight size={16} aria-hidden="true" />
            <span>Registrar Saída</span>
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadDashboard}
            disabled={loading}
          >
            <RefreshCw size={15} aria-hidden="true" />
            <span>Atualizar</span>
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

      <div className="filters-bar dashboard-period-bar">
        <div className="form-field" style={{ minWidth: 190 }}>
          <label htmlFor="dash-period">Período dos indicadores</label>
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

        {data ? (
          <div className="dashboard-ref-meta tabular-nums" data-testid="dashboard-reference-date">
            <Calendar size={14} aria-hidden="true" />
            <span>
              Período: <strong>{periodRangeLabel}</strong> · Data de referência:{" "}
              <strong>{referenceDateLabel}</strong>
            </span>
          </div>
        ) : null}
      </div>

      {loading && !data ? (
        <div className="card state-box">Carregando indicadores do painel...</div>
      ) : data ? (
        <>
          <section className="kpi-grid" aria-label="Indicadores principais de estoque">
            <article className="kpi-card primary">
              <div className="kpi-label">
                <span>Produtos Ativos</span>
                <Boxes size={16} color="var(--accent-primary)" aria-hidden="true" />
              </div>
              <div className="kpi-value">{data.active_products_count}</div>
              <div className="kpi-helper">Itens habilitados para movimentação</div>
              <Link
                to={isAdmin ? "/relatorios?tab=current-stock" : "/produtos"}
                className="kpi-link"
              >
                <span>{isAdmin ? "Ver relatório de estoque" : "Consultar catálogo"}</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </article>

            <article className="kpi-card danger">
              <div className="kpi-label">
                <span>Sem Estoque</span>
                <PackageX size={16} color="var(--state-danger-solid)" aria-hidden="true" />
              </div>
              <div className="kpi-value">{data.out_of_stock_count}</div>
              <div className="kpi-helper">Produtos ativos com saldo zero</div>
              <Link
                to={isAdmin ? "/relatorios?tab=below-minimum" : "/produtos"}
                className="kpi-link"
              >
                <span>{isAdmin ? "Ver itens críticos" : "Filtrar produtos"}</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </article>

            <article className="kpi-card warning">
              <div className="kpi-label">
                <span>Abaixo do Mínimo</span>
                <AlertCircle size={16} color="var(--state-warning-solid)" aria-hidden="true" />
              </div>
              <div className="kpi-value">{data.below_min_stock_count}</div>
              <div className="kpi-helper">Saldo abaixo do estoque mínimo definido</div>
              <Link
                to={isAdmin ? "/relatorios?tab=below-minimum" : "/produtos"}
                className="kpi-link"
              >
                <span>{isAdmin ? "Abrir relatório abaixo do mínimo" : "Ver saldos"}</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </article>

            <article className="kpi-card success">
              <div className="kpi-label">
                <span>Movimentações no Período</span>
                <ArrowUpRight size={16} color="var(--state-success-solid)" aria-hidden="true" />
              </div>
              <div className="kpi-value">
                {data.entries_count} ent. / {data.exits_count} saí.
              </div>
              <div className="kpi-helper">
                {data.adjustments_count} ajuste(s) · {data.reversals_count} estorno(s)
              </div>
              <Link
                to={isAdmin ? "/relatorios?tab=movements" : "/movimentacoes"}
                className="kpi-link"
              >
                <span>{isAdmin ? "Ver relatório de movimentações" : "Abrir histórico"}</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </article>

            <article className="kpi-card primary">
              <div className="kpi-label">
                <span>Valor Estimado</span>
                <DollarSign size={16} color="var(--accent-primary)" aria-hidden="true" />
              </div>
              <div className="kpi-value">
                {formatCurrencyBRL(data.estimated_stock_value_brl)}
              </div>
              <div className="kpi-helper">
                {data.valuation_formula}. <strong>Não é avaliação contábil.</strong>
              </div>
            </article>
          </section>

          <section className="card" style={{ marginBottom: 16 }}>
            <div className="card-title-row">
              <div>
                <h2>Tendência de Movimentações Diárias</h2>
                <p className="page-subtitle">
                  {selectedChartUnit === "ALL"
                    ? "Contagem diária de operações (selecione uma unidade específica para comparar quantidades exatas)."
                    : `Quantidades diárias movimentadas na unidade ${selectedChartUnit}.`}
                </p>
              </div>
              <div className="form-field" style={{ minWidth: 230 }}>
                <label htmlFor="chart-unit-select">Unidade / métrica do gráfico</label>
                <select
                  id="chart-unit-select"
                  className="select"
                  value={selectedChartUnit}
                  onChange={(e) => setSelectedChartUnit(e.target.value)}
                >
                  <option value="ALL">Todas as unidades (lançamentos/dia)</option>
                  {data.unit_summaries.map((u) => (
                    <option key={u.unit} value={u.unit}>
                      Quantidade em {u.unit} ({u.unit_label})
                    </option>
                  ))}
                </select>
              </div>
            </div>

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
                <h3>Sem movimentações no período selecionado</h3>
                <p>
                  Registre entradas ou saídas ou amplie o intervalo de datas para acompanhar a evolução diária.
                </p>
              </div>
            ) : (
              <>
                <div className="chart-container">
                  <div className="chart-bars" role="img" aria-label={`Gráfico de entradas e saídas em ${chartUnitLabel} de ${periodRangeLabel}`}>
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
                  {isAdmin ? (
                    <Link to="/relatorios?tab=movements" className="chart-legend-link">
                      <span>Abrir relatório de movimentações</span>
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                  ) : null}
                </div>
              </>
            )}
          </section>

          <section className="card" style={{ marginBottom: 16 }}>
            <div className="card-title-row">
              <div>
                <h2>Resumo por Unidade de Medida</h2>
                <p className="page-subtitle">
                  Totais do período agrupados por unidade, sem misturar grandezas incompatíveis.
                </p>
              </div>
              {isAdmin ? (
                <Link to="/relatorios?tab=current-stock" className="btn btn-secondary btn-sm">
                  <span>Relatório de Estoque Atual</span>
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              ) : null}
            </div>

            <div className="alert alert-info" style={{ marginBottom: 14 }}>
              <strong>Critério de valor estimado:</strong> {data.valuation_formula}.{" "}
              {data.valuation_disclaimer}
            </div>

            {data.unit_summaries.length === 0 ? (
              <div className="state-box">
                Nenhuma entrada ou saída registrada no período selecionado.
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Unidade</th>
                      <th className="td-numeric">Entradas no período</th>
                      <th className="td-numeric">Saídas totais</th>
                      <th className="td-numeric">Saídas de demanda (Venda/Consumo)</th>
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

          <section className="card">
            <div className="card-title-row">
              <div>
                <h2>Itens Sem Estoque ou Abaixo do Mínimo</h2>
                <p className="page-subtitle">
                  Produtos ativos ordenados por prioridade de reposição operacional.
                </p>
              </div>
              {isAdmin ? (
                <div className="header-actions">
                  <Link to="/relatorios?tab=below-minimum" className="btn btn-secondary btn-sm">
                    <span>Ver abaixo do mínimo</span>
                  </Link>
                  <Link to="/relatorios?tab=replenishment" className="btn btn-secondary btn-sm">
                    <span>Relatório de reposição</span>
                    <ArrowRight size={14} aria-hidden="true" />
                  </Link>
                </div>
              ) : null}
            </div>

            {data.replenishment_list.length === 0 ? (
              <div className="state-box">
                <h3>Estoque dentro dos parâmetros mínimos</h3>
                <p>
                  Todos os produtos ativos estão com saldo igual ou superior ao estoque mínimo configurado.
                </p>
              </div>
            ) : (
              <>
                {data.replenishment_list.length > 20 ? (
                  <p className="page-subtitle" style={{ marginBottom: 12 }}>
                    Exibindo os <strong>20</strong> primeiros itens prioritários de{" "}
                    <strong>{data.replenishment_list.length}</strong> retornados pelo painel.
                  </p>
                ) : null}
                <div
                  className="table-wrap"
                  role="region"
                  aria-label="Itens prioritários para reposição"
                  tabIndex={0}
                >
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>SKU</th>
                        <th>Produto</th>
                        <th className="td-numeric">Saldo Atual</th>
                        <th className="td-numeric">Mínimo</th>
                        <th className="td-numeric">Déficit</th>
                        <th>Fornecedor / Prazo</th>
                        <th>Situação</th>
                        <th>Ação Rápida</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.replenishment_list.slice(0, 20).map((item) => (
                      <tr key={item.product_id}>
                        <td className="mono">{item.sku}</td>
                        <td>
                          <strong>{item.name}</strong>
                          <div style={{ fontSize: "0.78rem", color: "var(--ink-muted)" }}>
                            {item.category_name}
                          </div>
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
                          {item.lead_time_days !== null
                            ? ` (${item.lead_time_days} d)`
                            : ""}
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              item.stock_status === "OUT_OF_STOCK"
                                ? "badge-danger"
                                : "badge-warning"
                            }`}
                          >
                            {item.stock_status === "OUT_OF_STOCK"
                              ? "Sem estoque"
                              : "Abaixo do mínimo"}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-success btn-sm"
                            onClick={() => openQuickMovement("ENTRADA", item.product_id)}
                          >
                            <ArrowDownLeft size={14} aria-hidden="true" />
                            <span>Registrar Entrada</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              </>
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
