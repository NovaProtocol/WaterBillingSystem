import { type PricingTier, type BreakdownItem } from '@/db/types';

function computeBill(
  consumption: number,
  tiers: PricingTier[]
): { total: number; breakdown: BreakdownItem[] } {
  let total = 0;
  const breakdown: BreakdownItem[] = [];
  for (const tier of tiers) {
    const unitsInTier =
      consumption <= tier.from_unit
        ? 0
        : Math.min(consumption, tier.to_unit) - tier.from_unit;
    const charge =
      tier.unit === 'flat' ? (unitsInTier > 0 ? tier.rate : 0) : unitsInTier * tier.rate;
    breakdown.push({ label: tier.label, units: unitsInTier, charge });
    total += charge;
  }
  return { total, breakdown };
}

const sampleTiers: PricingTier[] = [
  { label: 'First 10 m3', from_unit: 0, to_unit: 10, rate: 150, unit: 'flat' },
  { label: 'Next 10 m3', from_unit: 10, to_unit: 20, rate: 25, unit: 'per_unit' },
  { label: 'Over 20 m3', from_unit: 20, to_unit: Infinity, rate: 35, unit: 'per_unit' },
];

describe('computeBill', () => {
  test('zero consumption', () => {
    const result = computeBill(0, sampleTiers);
    expect(result.total).toBe(0);
    expect(result.breakdown.every(b => b.charge === 0)).toBe(true);
  });

  test('first tier flat rate', () => {
    const result = computeBill(5, sampleTiers);
    expect(result.total).toBe(150);
    expect(result.breakdown[0].charge).toBe(150);
  });

  test('second tier per-unit', () => {
    const result = computeBill(15, sampleTiers);
    expect(result.total).toBe(150 + 5 * 25);
  });

  test('third tier per-unit', () => {
    const result = computeBill(30, sampleTiers);
    expect(result.total).toBe(150 + 10 * 25 + 10 * 35);
  });

  test('boundary at tier edge', () => {
    const result = computeBill(10, sampleTiers);
    expect(result.total).toBe(150);
  });
});
