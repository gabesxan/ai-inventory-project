import { useCallback, useEffect, useState } from "react";
import { Info, Sparkles } from "lucide-react";
import { apiRequest, ApiError, buildQueryString } from "../services/api";
import type { PurchaseSuggestionsResponse } from "../types/api";
import { formatDateBR, formatQuantity } from "../utils/format";

export function PurchaseSuggestionsPage() {
  const [horizonDays, setHorizonDays] = useState("30");
  const [simulate, setSimulate] = useState(false);
  const [data, setData] = useState<PurchaseSuggestionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSuggestions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = buildQueryString({
        horizon_days: Number(horizonDays) || 30,
        simulate,
      });
      const res = await apiRequest<PurchaseSuggestionsResponse>(
        `/ai/purchase-suggestions${qs}`
      );
      setData(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Erro ao consultar sugestões de compra."
      );
    } finally {
      setLoading(false);
    }
  }, [horizonDays, simulate]);

  useEffect(() => {
    loadSuggestions();
  }, [loadSuggestions]);

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Sugestões de Compra (Preparação para IA)</h1>
          <p className="page-subtitle">
            Estrutura pronta para conectar o futuro modelo de previsão de demanda e apoiar decisões de reposição.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className={`btn ${simulate ? "btn-secondary" : "btn-primary"}`}
            onClick={() => setSimulate((prev) => !prev)}
          >
            <Sparkles size={16} />
            <span>
              {simulate
                ? "Ocultar Simulação Demonstrativa"
                : "Visualizar Simulação Demonstrativa (Média Móvel)"}
            </span>
          </button>
        </div>
      </div>

      {error ? (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      ) : null}

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="filters-bar" style={{ marginBottom: 0 }}>
          <div className="form-field" style={{ minWidth: 180 }}>
            <label htmlFor="ai-horizon">Horizonte de previsão (dias)</label>
            <select
              id="ai-horizon"
              className="select"
              value={horizonDays}
              onChange={(e) => setHorizonDays(e.target.value)}
            >
              <option value="15">15 dias</option>
              <option value="30">30 dias</option>
              <option value="60">60 dias</option>
              <option value="90">90 dias</option>
            </select>
          </div>
          <div style={{ flex: 1, fontSize: "0.88rem", color: "#475569" }}>
            {data?.replenishment_rule_note}
          </div>
        </div>
      </div>

      {loading && !data ? (
        <div className="card state-box">Carregando módulo de sugestões de compra...</div>
      ) : data ? (
        <>
          <div
            className={`alert ${data.is_simulated ? "alert-warning" : "alert-info"}`}
          >
            <Info size={18} style={{ flexShrink: 0, marginTop: 2 }} />
            <div>
              <strong>{data.status_title}:</strong> {data.status_message}
              <div style={{ marginTop: 6, fontSize: "0.86rem" }}>
                <strong>Governança:</strong> {data.human_decision_notice}
              </div>
            </div>
          </div>

          <div className="kpi-grid">
            <div className="kpi-card primary">
              <div className="kpi-label">Produtos Ativos</div>
              <div className="kpi-value">{data.data_readiness.active_products}</div>
              <div className="kpi-helper">Elegíveis para recomendação</div>
            </div>
            <div className="kpi-card success">
              <div className="kpi-label">Eventos de Demanda (Op.)</div>
              <div className="kpi-value">
                {data.data_readiness.operational_demand_events}
              </div>
              <div className="kpi-helper">
                De {data.data_readiness.operational_movements} movimentações operacionais
              </div>
            </div>
            <div className="kpi-card primary">
              <div className="kpi-label">Histórico Importado (Estudo)</div>
              <div className="kpi-value">
                {data.data_readiness.historical_study_movements}
              </div>
              <div className="kpi-helper">Base analítica para treino futuro</div>
            </div>
            <div className="kpi-card warning">
              <div className="kpi-label">Períodos de Ruptura</div>
              <div className="kpi-value">
                {data.data_readiness.stockout_periods_recorded}
              </div>
              <div className="kpi-helper">Dias sem estoque sinalizados para o modelo</div>
            </div>
          </div>

          {!data.is_simulated && data.items.length === 0 ? (
            <div className="card state-box">
              <h3>Aguardando integração do modelo preditivo</h3>
              <p>
                Nenhum modelo treinado foi conectado nesta v1. Continue registrando entradas,
                saídas padronizadas (Venda/Consumo vs Perda/Avaria) e importando séries históricas na
                aba <strong>Dados para IA</strong>.
              </p>
            </div>
          ) : (
            <div className="card">
              <div className="card-title-row">
                <div>
                  <h2>
                    Tabela de Recomendações{" "}
                    {data.is_simulated ? (
                      <span className="badge badge-warning" style={{ marginLeft: 8 }}>
                        SIMULAÇÃO DEMONSTRATIVA ({data.model_version})
                      </span>
                    ) : null}
                  </h2>
                  <p className="page-subtitle">
                    Cálculo de apoio humano sem emissão automática de pedido de compra.
                  </p>
                </div>
              </div>

              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th>Estoque Disponível</th>
                      <th>Demanda Prevista</th>
                      <th>Prazo Reposição</th>
                      <th>Qtd. Recomendada</th>
                      <th>Motivo da Recomendação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr key={item.product_id}>
                        <td>
                          <strong>{item.product_name}</strong>
                          <div className="mono" style={{ fontSize: "0.78rem", color: "#64748b" }}>
                            {item.sku} · Seg: {formatQuantity(item.safety_stock, item.unit)}{" "}
                            {item.unit}
                          </div>
                        </td>
                        <td>
                          <strong>
                            {formatQuantity(item.available_stock, item.unit)} {item.unit}
                          </strong>
                        </td>
                        <td>
                          <div>
                            <strong>
                              {formatQuantity(
                                item.predicted_demand_effective_window,
                                item.unit
                              )}{" "}
                              {item.unit}
                            </strong>{" "}
                            <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                              (janela {item.effective_coverage_days}d)
                            </span>
                          </div>
                          <div style={{ fontSize: "0.76rem", color: "#64748b" }}>
                            Horizonte {item.horizon_days}d ({formatDateBR(item.period_start)}–
                            {formatDateBR(item.period_end)}):{" "}
                            {formatQuantity(item.predicted_demand_horizon, item.unit)}{" "}
                            {item.unit}
                          </div>
                        </td>
                        <td>
                          {item.lead_time_days} dias
                          <div style={{ fontSize: "0.76rem", color: "#64748b" }}>
                            {item.lead_time_source}
                          </div>
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              Number(item.recommended_purchase_qty) > 0
                                ? "badge-warning"
                                : "badge-success"
                            }`}
                            style={{ fontSize: "0.88rem" }}
                          >
                            {formatQuantity(item.recommended_purchase_qty, item.unit)}{" "}
                            {item.unit}
                          </span>
                        </td>
                        <td style={{ maxWidth: 340, fontSize: "0.84rem" }}>
                          {item.reason_summary}
                          {item.is_simulated ? (
                            <div style={{ fontSize: "0.75rem", color: "#b45309", marginTop: 3 }}>
                              Simulado · Não substitui avaliação real.
                            </div>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
