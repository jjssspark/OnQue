export type HistoryEntryType = 'call' | 'document';

export type HistoryEntry = {
  id: string;
  type: HistoryEntryType;
  filename: string;
  summary: string;
  createdAt: string;
};

const STORAGE_KEY = 'onque.history.v1';
const MAX_ENTRIES = 200;

function readAll(): HistoryEntry[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function writeAll(entries: HistoryEntry[]): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
}

export function getHistory(): HistoryEntry[] {
  return readAll().sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function addHistoryEntry(
  entry: Omit<HistoryEntry, 'id' | 'createdAt'>
): HistoryEntry {
  const newEntry: HistoryEntry = {
    ...entry,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
  };

  const next = [newEntry, ...readAll()].slice(0, MAX_ENTRIES);
  writeAll(next);
  return newEntry;
}

export function deleteHistoryEntry(id: string): void {
  writeAll(readAll().filter((entry) => entry.id !== id));
}

export function searchHistory(
  query: string,
  type?: HistoryEntryType
): HistoryEntry[] {
  const normalized = query.trim().toLowerCase();

  return getHistory().filter((entry) => {
    if (type && entry.type !== type) return false;
    if (!normalized) return true;
    return (
      entry.filename.toLowerCase().includes(normalized) ||
      entry.summary.toLowerCase().includes(normalized)
    );
  });
}
