interface BrandMarkProps {
  size?: number;
  className?: string;
}

/**
 * Original geometric EstoqueFácil emblem: three stacked precision inventory layers
 * framed inside a rounded container.
 */
export function BrandMark({ size = 28, className }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="8" fill="currentColor" fillOpacity="0.12" />
      <rect
        x="0.75"
        y="0.75"
        width="30.5"
        height="30.5"
        rx="7.25"
        stroke="currentColor"
        strokeOpacity="0.24"
        strokeWidth="1.5"
      />
      <path
        d="M8.5 11.25L16 7.5L23.5 11.25L16 15L8.5 11.25Z"
        fill="currentColor"
      />
      <path
        d="M8.5 16L16 19.75L23.5 16"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8.5 20.75L16 24.5L23.5 20.75"
        stroke="currentColor"
        strokeOpacity="0.65"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
