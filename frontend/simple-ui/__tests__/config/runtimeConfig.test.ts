import {
  applyRuntimeConfig,
  DEFAULT_PLATFORM_NAME,
  getPlatformName,
  getServerRuntimeConfig,
} from '../../src/config/runtimeConfig';

const ENV_KEYS = ['PLATFORM_NAME', 'NEXT_PUBLIC_PLATFORM_NAME'] as const;

describe('getPlatformName', () => {
  afterEach(() => {
    applyRuntimeConfig({
      apiUrl: '',
      telemetryServiceUrl: '',
      enabledTaskTypes: '',
      platformName: DEFAULT_PLATFORM_NAME,
    });
  });

  it('falls back to AI Switch when unset', () => {
    expect(getPlatformName()).toBe('AI Switch');
    expect(getPlatformName()).toBe(DEFAULT_PLATFORM_NAME);
  });

  it('returns the applied runtime config value', () => {
    applyRuntimeConfig({
      apiUrl: '',
      telemetryServiceUrl: '',
      enabledTaskTypes: '',
      platformName: 'Custom Brand',
    });
    expect(getPlatformName()).toBe('Custom Brand');
  });

  it('falls back when the applied name is blank', () => {
    applyRuntimeConfig({
      apiUrl: '',
      telemetryServiceUrl: '',
      enabledTaskTypes: '',
      platformName: '   ',
    });
    expect(getPlatformName()).toBe(DEFAULT_PLATFORM_NAME);
  });
});

describe('getServerRuntimeConfig platformName', () => {
  const saved: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS) {
      saved[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (saved[key] === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = saved[key];
      }
    }
  });

  it('falls back to AI Switch when both env keys are empty', () => {
    expect(getServerRuntimeConfig().platformName).toBe(DEFAULT_PLATFORM_NAME);
  });

  it('reads PLATFORM_NAME', () => {
    process.env.PLATFORM_NAME = 'From Env';
    expect(getServerRuntimeConfig().platformName).toBe('From Env');
  });

  it('falls back to NEXT_PUBLIC_PLATFORM_NAME', () => {
    process.env.NEXT_PUBLIC_PLATFORM_NAME = 'Legacy Name';
    expect(getServerRuntimeConfig().platformName).toBe('Legacy Name');
  });

  it('prefers PLATFORM_NAME over the legacy key', () => {
    process.env.PLATFORM_NAME = 'Preferred';
    process.env.NEXT_PUBLIC_PLATFORM_NAME = 'Legacy Name';
    expect(getServerRuntimeConfig().platformName).toBe('Preferred');
  });

  it('treats whitespace-only PLATFORM_NAME as unset', () => {
    process.env.PLATFORM_NAME = '   ';
    expect(getServerRuntimeConfig().platformName).toBe(DEFAULT_PLATFORM_NAME);
  });
});
