const DISCRETE_UNITS = new Set(["UN", "CX", "PCT", "PAR", "FD", "RL"]);

const brlFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function isDiscreteUnitCode(unit: string): boolean {
  return DISCRETE_UNITS.has((unit || "").toUpperCase());
}

export function formatCurrencyBRL(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const num = typeof value === "number" ? value : Number(String(value).replace(",", "."));
  if (Number.isNaN(num)) return "—";
  return brlFormatter.format(num);
}

export function formatQuantity(
  value: number | string | null | undefined,
  unit: string
): string {
  if (value === null || value === undefined || value === "") return "0";
  const num = typeof value === "number" ? value : Number(String(value).replace(",", "."));
  if (Number.isNaN(num)) return "0";

  if (isDiscreteUnitCode(unit)) {
    return new Intl.NumberFormat("pt-BR", {
      maximumFractionDigits: 0,
    }).format(Math.round(num));
  }

  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  }).format(num);
}

export function formatDateBR(value: string | null | undefined): string {
  if (!value) return "—";
  // Trata datas puras YYYY-MM-DD sem deslocamento de fuso
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split("-");
    return `${d}/${m}/${y}`;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateFormatter.format(date);
}

export function formatDateTimeBR(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateTimeFormatter.format(date);
}

export function translateRole(role: string): string {
  return role === "ADMIN" ? "Administrador" : "Operador";
}

export function translateMovementType(type: string): string {
  const map: Record<string, string> = {
    ENTRADA: "Entrada",
    SAIDA: "Saída",
    AJUSTE: "Ajuste",
    ESTORNO: "Estorno",
  };
  return map[type] ?? type;
}

export function translateReasonCode(reason: string): string {
  const map: Record<string, string> = {
    RECEBIMENTO: "Recebimento",
    SALDO_INICIAL: "Saldo inicial",
    VENDA: "Venda",
    CONSUMO: "Consumo interno",
    PERDA: "Perda",
    AVARIA: "Avaria",
    OUTRO: "Outro",
    AJUSTE_POSITIVO: "Ajuste positivo",
    AJUSTE_NEGATIVO: "Ajuste negativo",
    ESTORNO: "Estorno",
  };
  return map[reason] ?? reason;
}

export function translateStockStatus(status: string): string {
  const map: Record<string, string> = {
    OUT_OF_STOCK: "Sem estoque",
    BELOW_MIN: "Abaixo do mínimo",
    OK: "Normal",
  };
  return map[status] ?? status;
}
