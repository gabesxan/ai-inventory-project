import { useEffect, useState } from "react";
import { AlertTriangle, Check } from "lucide-react";
import { Modal } from "./Modal";

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (reasonText: string) => Promise<void> | void;
  title: string;
  description: string;
  confirmLabel: string;
  confirmVariant?: "danger" | "primary";
  requireReason?: boolean;
  reasonLabel?: string;
  reasonPlaceholder?: string;
  isSubmitting?: boolean;
  errorMessage?: string | null;
}

export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel,
  confirmVariant = "danger",
  requireReason = false,
  reasonLabel = "Justificativa obrigatória",
  reasonPlaceholder = "Descreva o motivo (mínimo 5 caracteres)...",
  isSubmitting = false,
  errorMessage = null,
}: ConfirmModalProps) {
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setReason("");
      setLocalError(null);
    }
  }, [isOpen]);

  const handleConfirm = async () => {
    if (requireReason && reason.trim().length < 5) {
      setLocalError("Informe uma justificativa com pelo menos 5 caracteres.");
      return;
    }
    setLocalError(null);
    await onConfirm(reason.trim());
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancelar
          </button>
          <button
            type="button"
            className={`btn ${
              confirmVariant === "danger" ? "btn-danger" : "btn-primary"
            }`}
            onClick={handleConfirm}
            disabled={isSubmitting}
          >
            <Check size={16} />
            <span>{isSubmitting ? "Processando..." : confirmLabel}</span>
          </button>
        </>
      }
    >
      <div className="alert alert-warning" style={{ marginBottom: 14 }}>
        <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>{description}</div>
      </div>

      {errorMessage ? (
        <div className="alert alert-error" role="alert">
          {errorMessage}
        </div>
      ) : null}

      {requireReason ? (
        <div className="form-field">
          <label htmlFor="confirm-reason-input">{reasonLabel}</label>
          <textarea
            id="confirm-reason-input"
            className={`textarea ${localError ? "has-error" : ""}`}
            placeholder={reasonPlaceholder}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (localError) setLocalError(null);
            }}
            rows={3}
          />
          {localError ? <span className="field-error">{localError}</span> : null}
        </div>
      ) : null}
    </Modal>
  );
}
