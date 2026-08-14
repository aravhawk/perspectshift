export function formatBytes(value: number | null | undefined): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let n = value;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n < 10 && i > 0 ? n.toFixed(2) : n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatMs(value: number | null | undefined): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function formatBool(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value ? "yes" : "no";
}

export function truncateHash(value: string | null | undefined, len = 12): string {
  if (!value) {
    return "—";
  }
  return value.length <= len ? value : `${value.slice(0, len)}…`;
}
