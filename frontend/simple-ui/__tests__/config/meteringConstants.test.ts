import { METERING } from '../../src/config/meteringConstants';
import { meteringColorAt } from '../../src/utils/meteringColors';
import { inferModelTaskType, normalizeModelTaskType, resolveModelTaskType } from '../../src/utils/meteringTaskType';
import { buildTaskTypeConsumptionChart } from '../../src/utils/meteringFormatters';

describe('Usage Dashboard v2.0 (AI4IDS-2908)', () => {
  it('exposes three tabs with renamed labels', () => {
    expect(METERING.SUB_TABS).toHaveLength(3);
    expect(METERING.SUB_TABS.map((t) => t.label)).toEqual(['Institution', 'Model', 'Budget']);
    expect(METERING.SUB_TABS.map((t) => t.id)).toEqual(['overview', 'model', 'usage-spend']);
  });

  it('defaults usage concentration to Top 10', () => {
    expect(METERING.DEFAULTS.TOP_N).toBe(10);
    expect(METERING.TOP_N_OPTIONS).toEqual([10, 25]);
  });

  it('fetches enough ranking rows for the largest Top-N toggle', () => {
    const maxTopN = Math.max(...METERING.TOP_N_OPTIONS);
    expect(METERING.USAGE_CONCENTRATION_FETCH_LIMIT).toBeGreaterThanOrEqual(maxTopN);
    expect(METERING.COLORS.PALETTE.length).toBeGreaterThanOrEqual(maxTopN);
  });

  it('assigns a unique colour per rank up to Top 25', () => {
    const colors = Array.from({ length: 25 }, (_, i) => meteringColorAt(i));
    expect(new Set(colors).size).toBe(25);
  });

  it('does not reference Top 5 in usage concentration copy', () => {
    const { SUBTITLE } = METERING.SECTIONS.CONSUMPTION_OVERVIEW;
    expect(SUBTITLE.toLowerCase()).not.toContain('top 5');
  });
});

describe('Model Consumption tooltips (AI4IDS-2854, AI4IDS-2957)', () => {
  const { TOTAL_MODELS, ACTIVE_MODELS, TOKEN_CONSUMPTION } = METERING.SECTIONS.MODEL.TOOLTIPS;

  it('does not describe the removed name-collapsed identity', () => {
    expect(TOTAL_MODELS.toLowerCase()).not.toContain('collapsed by name');
    expect(TOTAL_MODELS.toLowerCase()).not.toContain('distinct model');
    expect(ACTIVE_MODELS.toLowerCase()).not.toContain('distinct model');
  });

  it('scopes model KPI tooltips to enabled task types, not LLM-only', () => {
    expect(TOTAL_MODELS.toLowerCase()).not.toContain('llm');
    expect(ACTIVE_MODELS.toLowerCase()).not.toContain('llm');
    expect(TOTAL_MODELS.toLowerCase()).toContain('enabled task type');
    expect(ACTIVE_MODELS.toLowerCase()).toContain('enabled task type');
  });

  it('uses Native units wording for the native column tooltip (AI4IDS-2956)', () => {
    expect(TOKEN_CONSUMPTION).toContain('Native units');
    expect(TOKEN_CONSUMPTION.toLowerCase()).not.toContain('tokens');
  });

  it('describes model VERSIONS, matching the version-grained KPI values', () => {
    expect(TOTAL_MODELS.toLowerCase()).toContain('version');
    expect(ACTIVE_MODELS.toLowerCase()).toContain('version');
  });
});

describe('Overview KPI labels (AI4IDS-2957)', () => {
  it('uses task-type-neutral request labels', () => {
    expect(METERING.KPI.LABELS.total_requests).toBe('Total Requests');
    expect(METERING.KPI.LABELS.total_requests.toLowerCase()).not.toContain('llm');
  });

  it('uses AI Model wording in overview KPI tooltips', () => {
    expect(METERING.KPI.TOOLTIPS.total_requests.toLowerCase()).toContain('ai model');
    expect(METERING.KPI.TOOLTIPS.successful.toLowerCase()).toContain('ai model');
  });
});

describe('Budget summary tooltips (AI4IDS-2957)', () => {
  it('describes budget-only totals', () => {
    const tips = METERING.USAGE_SPEND.TOOLTIPS;
    expect(tips.TOTAL_ALLOCATED.toLowerCase()).toContain('budget');
    expect(tips.TOTAL_ALLOCATED.toLowerCase()).not.toContain('token');
    expect(tips.TOTAL_USED.toLowerCase()).toContain('budget');
    expect(tips.TOTAL_REMAINING.toLowerCase()).toContain('budget');
  });
});

describe('inferModelTaskType', () => {
  it('reads task type from service_id prefix', () => {
    expect(inferModelTaskType('nmt/indic-en', 'NMT')).toBe('nmt');
    expect(inferModelTaskType('llm/gemma', 'LLM Service')).toBe('llm');
  });

  it('normalizes underscore keys to hyphen form', () => {
    expect(normalizeModelTaskType('language_detection')).toBe('language-detection');
  });
});

describe('resolveModelTaskType (AI4IDS-2980)', () => {
  it('prefers API task_type over service_id inference', () => {
    expect(
      resolveModelTaskType({
        service_id: 'llm/gemma',
        name: 'LLM',
        task_type: 'nmt',
      }),
    ).toBe('nmt');
  });
});

describe('buildTaskTypeConsumptionChart (AI4IDS-2980)', () => {
  it('aggregates requests by task type', () => {
    const { slices, totalRequests } = buildTaskTypeConsumptionChart([
      { task_type: 'llm', requests: 60 },
      { task_type: 'nmt', requests: 40 },
      { task_type: 'llm', requests: 20 },
    ]);
    expect(totalRequests).toBe(120);
    expect(slices).toHaveLength(2);
    expect(slices[0]?.name).toBe('LLM');
    expect(slices[0]?.value).toBe(80);
  });
});
