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
  return (
    <div className="pagination-bar">
      <span>
        Total de registros: <strong>{totalItems}</strong>
      </span>
      <div className="pagination-controls">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft size={16} />
          <span>Anterior</span>
        </button>
        <span>
          Página <strong>{page}</strong> de <strong>{Math.max(1, totalPages)}</strong>
        </span>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          <span>Próxima</span>
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
