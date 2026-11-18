import React, { useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, SlidersHorizontal } from "lucide-react";
import { apiRequest, ApiError } from "../services/api";
import type { Product, Supplier } from "../types/api";
import { formatQuantity, isDiscreteUnitCode } from "../utils/format";
import { Modal } from "./Modal";

export type MovementModalMode = "ENTRADA" | "SAIDA" | "AJUSTE";

interface MovementModalProps {
  isOpen: boolean;
  mode: MovementModalMode;
  products: Product[];
  suppliers: Supplier[];
  initialProductId?: number | null;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

export function MovementModal({
  isOpen,
  mode,
  products,
  suppliers,
  initialProductId = null,
  onClose,
  onSuccess,
}: MovementModalProps) {
  const activeProducts = products.filter((p) => p.is_active);
  const activeSuppliers = suppliers.filter((s) => s.is_active);

  const [productId, setProductId] = useState<string>("");
  const [quantity, setQuantity] = useState<string>("");
  const [entryReason, setEntryReason] = useState<"RECEBIMENTO" | "SALDO_INICIAL">(
    "RECEBIMENTO"
  );
  const [exitReason, setExitReason] = useState<
    "VENDA" | "CONSUMO" | "PERDA" | "AVARIA" | "OUTRO"
  >("VENDA");
  const [adjDirection, setAdjDirection] = useState<"POSITIVO" | "NEGATIVO">(
    "POSITIVO"
  );
  const [unitCost, setUnitCost] = useState<string>("");
  const [supplierId, setSupplierId] = useState<string>("");
  const [orderDate, setOrderDate] = useState<string>("");
  const [receivedDate, setReceivedDate] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const selectedProduct = activeProducts.find((p) => String(p.id) === productId) || null;

  useEffect(() => {
    if (!isOpen) return;
    const defaultId = initialProductId
      ? String(initialProductId)
      : activeProducts[0]
      ? String(activeProducts[0].id)
      : "";
    setProductId(defaultId);
    setQuantity("");
    setEntryReason("RECEBIMENTO");
    setExitReason("VENDA");
    setAdjDirection("POSITIVO");
    const prod = activeProducts.find((p) => String(p.id) === defaultId);
    setUnitCost(prod ? String(prod.unit_cost) : "");
    setSupplierId(
      prod?.preferred_supplier_id ? String(prod.preferred_supplier_id) : ""
    );
    setOrderDate("");
    setReceivedDate("");
    setNotes("");
    setFieldErrors({});
    setSubmitError(null);
  }, [isOpen, initialProductId, mode]);

  const handleProductChange = (newId: string) => {
    setProductId(newId);
    const prod = activeProducts.find((p) => String(p.id) === newId);
    if (prod && mode === "ENTRADA") {
      setUnitCost(String(prod.unit_cost));
      setSupplierId(
        prod.preferred_supplier_id ? String(prod.preferred_supplier_id) : ""
      );
    }
    setFieldErrors({});
    setSubmitError(null);
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!selectedProduct) {
      errors.productId = "Selecione um produto ativo.";
    }
    const normalizedQty = Number(quantity.replace(",", "."));
    if (!quantity.trim() || Number.isNaN(normalizedQty) || normalizedQty <= 0) {
      errors.quantity = "Informe uma quantidade maior que zero.";
    } else if (selectedProduct && isDiscreteUnitCode(selectedProduct.unit)) {
      if (!Number.isInteger(normalizedQty)) {
        errors.quantity = `A unidade ${selectedProduct.unit} aceita apenas números inteiros.`;
      }
    }

    if (mode === "ENTRADA") {
      if (unitCost.trim()) {
        const costNum = Number(unitCost.replace(",", "."));
        if (Number.isNaN(costNum) || costNum < 0) {
          errors.unitCost = "Informe um custo unitário válido (>= 0).";
        }
      }
      if (orderDate && receivedDate && receivedDate < orderDate) {
        errors.receivedDate =
          "A data de recebimento não pode ser anterior à data do pedido.";
      }
    }

    if (mode === "AJUSTE" && notes.trim().length < 5) {
      errors.notes = "Justificativa obrigatória com ao menos 5 caracteres.";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate() || !selectedProduct) return;

    setSubmitting(true);
    setSubmitError(null);
    const qtyValue = quantity.replace(",", ".").trim();

    try {
      if (mode === "ENTRADA") {
        await apiRequest("/movements/entry", {
          method: "POST",
          body: JSON.stringify({
            product_id: selectedProduct.id,
            quantity: qtyValue,
            reason_code: entryReason,
            unit_cost: unitCost.trim() ? unitCost.replace(",", ".").trim() : null,
            supplier_id: supplierId ? Number(supplierId) : null,
            order_date: orderDate || null,
            received_date: receivedDate || null,
            notes: notes.trim() || null,
          }),
        });
        onSuccess(
          `Entrada registrada para ${selectedProduct.name} (${qtyValue} ${selectedProduct.unit}).`
        );
      } else if (mode === "SAIDA") {
        await apiRequest("/movements/exit", {
          method: "POST",
          body: JSON.stringify({
            product_id: selectedProduct.id,
            quantity: qtyValue,
            reason_code: exitReason,
            notes: notes.trim() || null,
          }),
        });
        onSuccess(
          `Saída registrada para ${selectedProduct.name} (${qtyValue} ${selectedProduct.unit}).`
        );
      } else {
        await apiRequest("/movements/adjustment", {
          method: "POST",
          body: JSON.stringify({
            product_id: selectedProduct.id,
            direction: adjDirection,
            quantity: qtyValue,
            notes: notes.trim(),
          }),
        });
        onSuccess(`Ajuste registrado para ${selectedProduct.name}.`);
      }
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(err.message);
      } else {
        setSubmitError("Não foi possível concluir a movimentação.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const modalTitle =
    mode === "ENTRADA"
      ? "Registrar Entrada no Estoque"
      : mode === "SAIDA"
      ? "Registrar Saída do Estoque"
      : "Registrar Ajuste de Inventário";

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={modalTitle}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={submitting}
          >
            Cancelar
          </button>
          <button
            type="submit"
            form="movement-modal-form"
            className={`btn ${
              mode === "ENTRADA"
                ? "btn-success"
                : mode === "SAIDA"
                ? "btn-primary"
                : "btn-danger"
            }`}
            disabled={submitting || activeProducts.length === 0}
          >
            {mode === "ENTRADA" ? (
              <ArrowDownLeft size={16} />
            ) : mode === "SAIDA" ? (
              <ArrowUpRight size={16} />
            ) : (
              <SlidersHorizontal size={16} />
            )}
            <span>{submitting ? "Salvando..." : "Confirmar Movimentação"}</span>
          </button>
        </>
      }
    >
      {submitError ? (
        <div className="alert alert-error" role="alert">
          {submitError}
        </div>
      ) : null}

      {activeProducts.length === 0 ? (
        <div className="alert alert-warning">
          Nenhum produto ativo cadastrado para movimentar.
        </div>
      ) : (
        <form id="movement-modal-form" onSubmit={handleSubmit} className="form-grid">
          <div className="form-field full">
            <label htmlFor="mv-product">Produto *</label>
            <select
              id="mv-product"
              className={`select ${fieldErrors.productId ? "has-error" : ""}`}
              value={productId}
              onChange={(e) => handleProductChange(e.target.value)}
            >
              {activeProducts.map((p) => (
                <option key={p.id} value={p.id}>
                  [{p.sku}] {p.name} — Saldo: {formatQuantity(p.current_stock, p.unit)}{" "}
                  {p.unit}
                </option>
              ))}
            </select>
            {selectedProduct ? (
              <span className="form-hint">
                Saldo atual disponível:{" "}
                <strong>
                  {formatQuantity(selectedProduct.current_stock, selectedProduct.unit)}{" "}
                  {selectedProduct.unit}
                </strong>{" "}
                ({selectedProduct.is_discrete_unit ? "apenas inteiros" : "até 3 decimais"})
              </span>
            ) : null}
            {fieldErrors.productId ? (
              <span className="field-error">{fieldErrors.productId}</span>
            ) : null}
          </div>

          <div className="form-field">
            <label htmlFor="mv-qty">
              Quantidade {selectedProduct ? `(${selectedProduct.unit})` : ""} *
            </label>
            <input
              id="mv-qty"
              type="number"
              min="0"
              step={selectedProduct?.is_discrete_unit ? "1" : "0.001"}
              className={`input ${fieldErrors.quantity ? "has-error" : ""}`}
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              placeholder={selectedProduct?.is_discrete_unit ? "Ex: 10" : "Ex: 2.500"}
            />
            {fieldErrors.quantity ? (
              <span className="field-error">{fieldErrors.quantity}</span>
            ) : null}
          </div>

          {mode === "ENTRADA" ? (
            <>
              <div className="form-field">
                <label htmlFor="mv-entry-reason">Tipo de Entrada *</label>
                <select
                  id="mv-entry-reason"
                  className="select"
                  value={entryReason}
                  onChange={(e) =>
                    setEntryReason(e.target.value as "RECEBIMENTO" | "SALDO_INICIAL")
                  }
                >
                  <option value="RECEBIMENTO">Recebimento de compra/reposição</option>
                  <option value="SALDO_INICIAL">Saldo inicial de implantação</option>
                </select>
              </div>

              <div className="form-field">
                <label htmlFor="mv-unit-cost">Custo Unitário na Entrada (R$)</label>
                <input
                  id="mv-unit-cost"
                  type="number"
                  min="0"
                  step="0.01"
                  className={`input ${fieldErrors.unitCost ? "has-error" : ""}`}
                  value={unitCost}
                  onChange={(e) => setUnitCost(e.target.value)}
                />
                <span className="form-hint">
                  Preservado no histórico para análises de custo e IA.
                </span>
                {fieldErrors.unitCost ? (
                  <span className="field-error">{fieldErrors.unitCost}</span>
                ) : null}
              </div>

              <div className="form-field">
                <label htmlFor="mv-supplier">Fornecedor (opcional)</label>
                <select
                  id="mv-supplier"
                  className="select"
                  value={supplierId}
                  onChange={(e) => setSupplierId(e.target.value)}
                >
                  <option value="">Sem fornecedor informado</option>
                  {activeSuppliers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-field">
                <label htmlFor="mv-order-date">Data do Pedido (opcional)</label>
                <input
                  id="mv-order-date"
                  type="date"
                  className="input"
                  value={orderDate}
                  onChange={(e) => setOrderDate(e.target.value)}
                />
              </div>

              <div className="form-field">
                <label htmlFor="mv-received-date">Data do Recebimento (opcional)</label>
                <input
                  id="mv-received-date"
                  type="date"
                  className={`input ${fieldErrors.receivedDate ? "has-error" : ""}`}
                  value={receivedDate}
                  onChange={(e) => setReceivedDate(e.target.value)}
                />
                {fieldErrors.receivedDate ? (
                  <span className="field-error">{fieldErrors.receivedDate}</span>
                ) : null}
              </div>
            </>
          ) : null}

          {mode === "SAIDA" ? (
            <div className="form-field">
              <label htmlFor="mv-exit-reason">Motivo Padronizado *</label>
              <select
                id="mv-exit-reason"
                className="select"
                value={exitReason}
                onChange={(e) =>
                  setExitReason(
                    e.target.value as
                      | "VENDA"
                      | "CONSUMO"
                      | "PERDA"
                      | "AVARIA"
                      | "OUTRO"
                  )
                }
              >
                <option value="VENDA">Venda (representa demanda)</option>
                <option value="CONSUMO">Consumo interno (representa demanda)</option>
                <option value="PERDA">Perda (não conta como demanda)</option>
                <option value="AVARIA">Avaria / dano (não conta como demanda)</option>
                <option value="OUTRO">Outro motivo (não conta como demanda)</option>
              </select>
            </div>
          ) : null}

          {mode === "AJUSTE" ? (
            <div className="form-field">
              <label htmlFor="mv-adj-dir">Direção do Ajuste *</label>
              <select
                id="mv-adj-dir"
                className="select"
                value={adjDirection}
                onChange={(e) =>
                  setAdjDirection(e.target.value as "POSITIVO" | "NEGATIVO")
                }
              >
                <option value="POSITIVO">Ajuste Positivo (+)</option>
                <option value="NEGATIVO">Ajuste Negativo (-)</option>
              </select>
            </div>
          ) : null}

          <div className="form-field full">
            <label htmlFor="mv-notes">
              {mode === "AJUSTE"
                ? "Justificativa obrigatória *"
                : "Observação / Motivo complementar"}
            </label>
            <textarea
              id="mv-notes"
              className={`textarea ${fieldErrors.notes ? "has-error" : ""}`}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={
                mode === "AJUSTE"
                  ? "Ex: Diferença identificada na contagem física mensal..."
                  : "Ex: NF 4512, lote A, requisição de setor..."
              }
            />
            {fieldErrors.notes ? (
              <span className="field-error">{fieldErrors.notes}</span>
            ) : null}
          </div>
        </form>
      )}
    </Modal>
  );
}
