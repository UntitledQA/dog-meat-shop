/** Форматирование дат для интерфейса. Бэкенд отдаёт ISO 8601 UTC. */

const MONTHS_GENITIVE = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
];

function parse(value: string | null | undefined): Date | null {
  if (!value) return null;
  // «2026-09-08» трактуем как локальную дату, чтобы не съезжал день из-за UTC.
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = dateOnly ? new Date(value + 'T00:00:00') : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** «8 сентября 2026» */
export function formatDate(value: string | null | undefined): string {
  const date = parse(value);
  if (!date) return '—';
  return date.getDate() + ' ' + MONTHS_GENITIVE[date.getMonth()] + ' ' + date.getFullYear();
}

/** «8 сентября 2026, 14:35» */
export function formatDateTime(value: string | null | undefined): string {
  const date = parse(value);
  if (!date) return '—';
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return formatDate(value) + ', ' + hours + ':' + minutes;
}

/** «08.09.2026» — компактный вид для списков. */
export function formatDateShort(value: string | null | undefined): string {
  const date = parse(value);
  if (!date) return '—';
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return day + '.' + month + '.' + date.getFullYear();
}

/** Дата через N дней в формате YYYY-MM-DD (для значения по умолчанию). */
export function isoDatePlusDays(days: number, now: Date = new Date()): string {
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return date.getFullYear() + '-' + month + '-' + day;
}
