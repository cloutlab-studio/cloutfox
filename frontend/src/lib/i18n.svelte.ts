// Strings come from src/core/strings.py (both languages live there); the page
// gets the active table at boot and after a language switch.

const state = $state({ table: {} as Record<string, string>, language: "ru" });

export function setStrings(language: string, table: Record<string, string>): void {
  state.language = language;
  state.table = table;
  document.documentElement.lang = language;
}

export function language(): string {
  return state.language;
}

/** Python str.format placeholders: "{name}" and "{count}". */
export function format(text: string, vars: Record<string, unknown> = {}): string {
  return text.replace(/\{(\w+)\}/g, (whole, key: string) =>
    key in vars ? String(vars[key]) : whole,
  );
}

export function t(key: string, vars?: Record<string, unknown>): string {
  return format(state.table[key] ?? key, vars);
}
