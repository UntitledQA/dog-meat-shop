import { describe, expect, it } from 'vitest';
import {
  DAY_OFF,
  DELIVERY_NOTE,
  DELIVERY_TERMS,
  PICKUP_ADDRESS_FALLBACK,
  PICKUP_NOTE,
  WORK_HOURS,
  WORK_SCHEDULE,
} from './deliveryInfo';

describe('график работы', () => {
  it('содержит все семь дней недели по порядку', () => {
    expect(WORK_SCHEDULE).toHaveLength(7);
    expect(WORK_SCHEDULE.map((day) => day.day)).toEqual([
      'ПН',
      'ВТ',
      'СР',
      'ЧТ',
      'ПТ',
      'СБ',
      'ВС',
    ]);
  });

  it('выходные — понедельник и четверг', () => {
    const daysOff = WORK_SCHEDULE.filter((day) => day.isDayOff);
    expect(daysOff.map((day) => day.day)).toEqual(['ПН', 'ЧТ']);
    for (const day of daysOff) {
      expect(day.hours).toBe(DAY_OFF);
    }
  });

  it('рабочие дни — с 10:00 до 18:00', () => {
    const workdays = WORK_SCHEDULE.filter((day) => !day.isDayOff);
    expect(workdays).toHaveLength(5);
    for (const day of workdays) {
      expect(day.hours).toBe(WORK_HOURS);
      expect(day.hours).toContain('10:00');
      expect(day.hours).toContain('18:00');
    }
  });
});

describe('условия доставки', () => {
  it('описывают своего курьера и inDrive', () => {
    expect(DELIVERY_TERMS).toHaveLength(2);
    const text = DELIVERY_TERMS.map((term) => term.label + ' ' + term.value).join(' ');
    expect(text).toContain('18:30');
    expect(text).toContain('22:00');
    expect(text).toContain('inDrive');
  });
});

describe('тексты условий доставки', () => {
  /** Все пользовательские строки модуля в одном списке. */
  const strings = [
    DELIVERY_NOTE,
    PICKUP_NOTE,
    PICKUP_ADDRESS_FALLBACK,
    DAY_OFF,
    WORK_HOURS,
    ...DELIVERY_TERMS.flatMap((term) => [term.label, term.value]),
    ...WORK_SCHEDULE.flatMap((day) => [day.day, day.hours]),
  ];

  it('не содержат HTML-сущностей: символа & нет ни в одной строке', () => {
    for (const value of strings) {
      expect(value).not.toContain('&');
    }
  });

  it('не содержат пустых строк', () => {
    for (const value of strings) {
      expect(value.trim()).not.toBe('');
    }
  });
});
