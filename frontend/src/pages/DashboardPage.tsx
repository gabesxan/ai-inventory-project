import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight,
  Boxes,
  DollarSign,
  PackageX,
  RefreshCw,
} from "lucide-react";
import { MovementModal, type MovementModalMode } from "../components/MovementModal";
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

  const openQuickMovement = (mode: MovementModalMode, productId?: number) => {
    setModalMode(mode);
    setModalProductId(productId ?? null);
    setModalOpen(true);
  };

  const chartPoints = data?.daily_chart || [];
  const visibleChartPoints =
    chartPoints.length > 31 ? chartPoints.slice(chartPoints.length - 31) : chartPoints;

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

  const maxChartValue = Math.max(
    1,
    ...visibleChartPoints.map((pt) => {
      const { inVal, outVal } = getChartValues(pt);
      return Math.max(inVal, outVal);
    })
  );

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Painel de Estoque</h1>
          <p className="page-subtitle">
            Indicadores calculados em tempo real a partir das movimentações registradas.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="btn btn-success"
            onClick={() => openQuickMovement("ENTRADA")}
          >
            <ArrowDownLeft size={16} />
            <span>Registrar Entrada</span>
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => openQuickMovement("SAIDA")}
          >
            <ArrowUpRight size={16} />
            <span>Registrar Saída</span>
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadDashboard}
            disabled={loading}
          >
            <RefreshCw size={16} />
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

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="filters-bar" style={{ marginBottom: 0 }}>
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
            <div style={{ marginLeft: "auto", fontSize: "0.86rem", color: "#475569" }}>
              Exibindo de <strong>{formatDateBR(data.period_start)}</strong> até{" "}
              <strong>{formatDateBR(data.period_end)}</strong>
            </div>
          ) : null}
        </div>
      </div>

      {loading && !data ? (
        <div className="card state-box">Carregando indicadores do painel...</div>
      ) : data ? (
        <>
          <div className="kpi-grid">
            <div className="kpi-card primary">
              <div className="kpi-label">
                <span>Produtos Ativos</span>
                <Boxes size={18} color="#1d4ed8" />
              </div>
              <div className="kpi-value">{data.active_products_count}</div>
              <div className="kpi-helper">Itens habilitados para movimentação</div>
            </div>

            <div className="kpi-card danger">
              <div className="kpi-label">
                <span>Sem Estoque</span>
                <PackageX size={18} color="#b91c1c" />
              </div>
              <div className="kpi-value">{data.out_of_stock_count}</div>
              <div className="kpi-helper">Produtos ativos com saldo zero</div>
            </div>

            <div className="kpi-card warning">
              <div className="kpi-label">
                <span>Abaixo do Mínimo</span>
                <AlertCircle size={18} color="#b45309" />
              </div>
              <div className="kpi-value">{data.below_min_stock_count}</div>
              <div className="kpi-helper">Saldo atual menor que o estoque mínimo</div>
            </div>

            <div className="kpi-card success">
              <div className="kpi-label">
                <span>Movimentações no Período</span>
                <ArrowLeftRightBadge />
              </div>
              <div className="kpi-value">
                {data.entries_count} ent. / {data.exits_count} saí.
              </div>
              <div className="kpi-helper">
                Contagem de lançamentos ({data.adjustments_count} ajustes,{" "}
                {data.reversals_count} estornos)
              </div>
            </div>

            <div className="kpi-card primary">
              <div className="kpi-label">
                <span>Valor Estimado do Estoque</span>
                <DollarSign size={18} color="#1d4ed8" />
              </div>
              <div className="kpi-value">
                {formatCurrencyBRL(data.estimated_stock_value_brl)}
              </div>
              <div className="kpi-helper">
                Cálculo: saldo atual × custo unitário de referência.{" "}
                <strong>Não é avaliação contábil.</strong>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 18 }}>
            <div className="card-title-row">
              <div>
                <h2>Movimentações por Unidade (sem misturar unidades incompatíveis)</h2>
                <p className="page-subtitle">
                  Totais do período separados por unidade de medida e definição de valor estimado.
                </p>
              </div>
            </div>

            <div className="alert alert-info" style={{ marginBottom: 14 }}>
              <div>
                <strong>Definição do Valor Estimado:</strong> {data.valuation_formula}.{" "}
                {data.valuation_disclaimer}
              </div>
            </div>

            {data.unit_summaries.length === 0 ? (
              <p className="page-subtitle">
                Nenhuma entrada ou saída registrada no período selecionado.
              </p>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Unidade</th>
                      <th>Entradas no período</th>
                      <th>Saídas totais</th>
                      <th>Saídas de demanda (Venda/Consumo)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.unit_summaries.map((u) => (
                      <tr key={u.unit}>
                        <td>
                          <strong>{u.unit}</strong> — {u.unit_label}
                        </td>
                        <td>
                          {formatQuantity(u.entries_qty, u.unit)} {u.unit}
                        </td>
                        <td>
                          {formatQuantity(u.exits_qty, u.unit)} {u.unit}
                        </td>
                        <td>
                          {formatQuantity(u.demand_exits_qty, u.unit)} {u.unit}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card" style={{ marginBottom: 18 }}>
            <div className="card-title-row">
              <div>
                <h2>Gráfico de Movimentações por Período</h2>
                <p className="page-subtitle">
                  {selectedChartUnit === "ALL"
                    ? "Exibindo número de operações diárias (para visualizar quantidades exatas, filtre por uma única unidade)."
                    : `Exibindo quantidades diárias na unidade ${selectedChartUnit}.`}
                </p>
              </div>
              <div className="form-field" style={{ minWidth: 220 }}>
                <label htmlFor="chart-unit-select">Métrica do gráfico</label>
                <select
                  id="chart-unit-select"
                  className="select"
                  value={selectedChartUnit}
                  onChange={(e) => setSelectedChartUnit(e.target.value)}
                >
                  <option value="ALL">Todas as unidades (nº de lançamentos)</option>
                  {data.unit_summaries.map((u) => (
                    <option key={u.unit} value={u.unit}>
                      Quantidade em {u.unit} ({u.unit_label})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {visibleChartPoints.length === 0 ? (
              <div className="state-box">Sem dados para exibir no gráfico.</div>
            ) : (
              <>
                <div className="chart-container">
                  <div className="chart-bars">
                    {visibleChartPoints.map((pt) => {
                      const { inVal, outVal } = getChartValues(pt);
                      const inHeight = Math.round((inVal / maxChartValue) * 130);
                      const outHeight = Math.round((outVal / maxChartValue) * 130);
                      return (
                        <div
                          key={pt.date}
                          className="chart-day"
                          title={`${formatDateBR(pt.date)} — Entradas: ${inVal} | Saídas: ${outVal}`}
                        >
                          <div className="chart-pair">
                            <div
                              className="chart-bar entry"
                              style={{ height: `${Math.max(2, inHeight)}px` }}
                            />
                            <div
                              className="chart-bar exit"
                              style={{ height: `${Math.max(2, outHeight)}px` }}
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
                    <span className="legend-dot" style={{ background: "#16a34a" }} />
                    Entradas
                  </span>
                  <span>
                    <span className="legend-dot" style={{ background: "#2563eb" }} />
                    Saídas
                  </span>
                </div>
              </>
            )}
          </div>

          <div className="card">
            <div className="card-title-row">
              <div>
                <h2>Lista de Reposição Prioritária</h2>
                <p className="page-subtitle">
                  Produtos ativos sem estoque ou com saldo abaixo do estoque mínimo.
                </p>
              </div>
            </div>

            {data.replenishment_list.length === 0 ? (
              <div className="state-box">
                Todos os produtos ativos estão com saldo igual ou superior ao estoque mínimo.
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Produto</th>
                      <th>Saldo Atual</th>
                      <th>Mínimo</th>
                      <th>Déficit</th>
                      <th>Fornecedor / Prazo</th>
                      <th>Situação</th>
                      <th>Ação Rápida</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.replenishment_list.map((item) => (
                      <tr key={item.product_id}>
                        <td className="mono">{item.sku}</td>
                        <td>
                          <strong>{item.name}</strong>
                          <div style={{ fontSize: "0.78rem", color: "#64748b" }}>
                            {item.category_name}
                          </div>
                        </td>
                        <td>
                          <strong>
                            {formatQuantity(item.current_stock, item.unit)} {item.unit}
                          </strong>
                        </td>
                        <td>
                          {formatQuantity(item.min_stock, item.unit)} {item.unit}
                        </td>
                        <td>
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
                            <ArrowDownLeft size={14} />
                            <span>Registrar Entrada</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
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

function ArrowLeftRightBadge() {
  return <ArrowUpRight size={18} color="#15803d" />;
}
