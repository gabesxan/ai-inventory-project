import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  totalPages: number;
  totalItems: number;
  onPageChange: (nextPage: number) => void;
}

export function Pagination({
  page,
  totalPages,
  totalItems,
  onPageChange,
}: PaginationProps) {
  const safeTotalPages = Math.max(1, totalPages);

  return (
    <nav className="pagination-bar" aria-label="Paginação de registros">
      <span className="pagination-summary tabular-nums">
        Total de registros: <strong>{totalItems}</strong>
      </span>
      <div className="pagination-controls">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft size={15} aria-hidden="true" />
          <span>Anterior</span>
        </button>
        <span className="pagination-indicator tabular-nums">
          Página <strong>{page}</strong> de <strong>{safeTotalPages}</strong>
        </span>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page >= safeTotalPages}
          onClick={() => onPageChange(page + 1)}
        >
          <span>Próxima</span>
          <ChevronRight size={15} aria-hidden="true" />
        </button>
      </div>
    </nav>
  );
}
