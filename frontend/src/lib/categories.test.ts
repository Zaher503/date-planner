import { describe, expect, it } from 'vitest';
import { CATEGORY_FILTERS, categoryFilterOn, categoryTokens, toggleCategoryFilter } from './categories';

const food = CATEGORY_FILTERS[0].cats;

describe('category filters', () => {
  it('turns a whole group on and off', () => {
    const on = toggleCategoryFilter(food, ['museum']);
    expect(on).toEqual(['museum', ...food]);
    expect(categoryFilterOn(food, { cats: on })).toBe(true);
    expect(toggleCategoryFilter(food, on)).toEqual(['museum']);
  });

  it('is not on when only part of a group is selected', () => {
    expect(categoryFilterOn(food, { cats: ['bar'] })).toBe(false);
    expect(categoryFilterOn(food, { cats: [] })).toBe(false);
  });

  it('adds only the missing categories of a half-selected group', () => {
    expect(toggleCategoryFilter(food, ['bar'])).toEqual(['bar', 'restaurant', 'cafe', 'dessert', 'nightlife']);
  });

  it('shows a group as one token and strays on their own', () => {
    const tokens = categoryTokens([...food, 'spa']);
    expect(tokens.map((t) => t.label)).toEqual(['Food & drinks', 'Spa']);
    expect(tokens[0].remove([...food, 'spa'])).toEqual(['spa']);
  });
});
