import { METERING } from '../../src/config/meteringConstants';

describe('Usage Dashboard v2.0 (AI4IDS-2908)', () => {
  it('exposes three adopter tabs with renamed labels', () => {
    expect(METERING.SUB_TABS).toHaveLength(3);
    expect(METERING.SUB_TABS.map((t) => t.label)).toEqual(['Institution', 'Model', 'Budget']);
    expect(METERING.SUB_TABS.map((t) => t.id)).toEqual(['overview', 'model', 'usage-spend']);
  });

  it('defaults usage concentration to Top 10', () => {
    expect(METERING.DEFAULTS.TOP_N).toBe(10);
    expect(METERING.TOP_N_OPTIONS).toEqual([10, 25]);
  });

  it('does not reference Top 5 in usage concentration copy', () => {
    const { SUBTITLE } = METERING.SECTIONS.CONSUMPTION_OVERVIEW;
    expect(SUBTITLE.toLowerCase()).not.toContain('top 5');
  });
});

describe('Model Consumption tooltips (AI4IDS-2854)', () => {
  const { TOTAL_MODELS, ACTIVE_MODELS } = METERING.SECTIONS.MODEL.TOOLTIPS;

  it('does not describe the removed name-collapsed identity', () => {
    // Backend now counts LLM model VERSIONS (model_id-grained), not distinct
    // names — this phrasing described the old, replaced behaviour and must
    // not silently come back.
    expect(TOTAL_MODELS.toLowerCase()).not.toContain('collapsed by name');
    expect(TOTAL_MODELS.toLowerCase()).not.toContain('distinct model');
    expect(ACTIVE_MODELS.toLowerCase()).not.toContain('distinct model');
  });

  it('states the LLM-only scope for both cards', () => {
    expect(TOTAL_MODELS.toLowerCase()).toContain('llm');
    expect(ACTIVE_MODELS.toLowerCase()).toContain('llm');
  });

  it('describes model VERSIONS, matching the version-grained KPI values', () => {
    expect(TOTAL_MODELS.toLowerCase()).toContain('version');
    expect(ACTIVE_MODELS.toLowerCase()).toContain('version');
  });
});
