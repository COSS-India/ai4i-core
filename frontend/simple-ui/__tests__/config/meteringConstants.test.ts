import { METERING } from '../../src/config/meteringConstants';

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
