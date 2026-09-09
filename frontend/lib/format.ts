const CATEGORY_LABELS: Record<string, string> = {
  artifact: "Hiện vật",
  document: "Tư liệu",
  photograph: "Ảnh tư liệu",
  historical_map: "Bản đồ lịch sử",
  exhibition_panel: "Bảng trưng bày",
  military_equipment: "Trang bị quân sự",
  personal_item: "Đồ dùng cá nhân",
  artwork: "Tác phẩm",
};

export function formatCategory(value?: string | null): string {
  if (!value) return "Tư liệu lịch sử";
  return (
    CATEGORY_LABELS[value] ||
    value
      .replaceAll("_", " ")
      .replaceAll("-", " ")
      .replace(/^./, (letter) => letter.toUpperCase())
  );
}

export function formatPeriod(
  period?: string | null,
  year?: number | null,
): string {
  if (period && year) return `${period} · ${year}`;
  return period || (year ? String(year) : "Chưa xác định niên đại");
}

export function formatSimilarity(score: number): string {
  const clamped = Math.max(-1, Math.min(1, score));
  return clamped.toLocaleString("vi-VN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatDuration(milliseconds?: number): string | null {
  if (milliseconds == null || !Number.isFinite(milliseconds)) return null;
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  return `${(milliseconds / 1000).toLocaleString("vi-VN", {
    maximumFractionDigits: 1,
  })} giây`;
}
