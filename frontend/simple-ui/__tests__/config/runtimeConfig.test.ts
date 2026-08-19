import {
  applyRuntimeConfig,
  DEFAULT_ADOPTER_LOGO_SRC,
  DEFAULT_PLATFORM_NAME,
  EMPTY_RUNTIME_CONFIG,
  getAdopterLogoSrc,
  getPlatformName,
  getServerRuntimeConfig,
} from '../../src/config/runtimeConfig';

const ENV_KEYS = [
  'PLATFORM_NAME',
  'NEXT_PUBLIC_PLATFORM_NAME',
  'ADOPTER_LOGO_URL',
  'NEXT_PUBLIC_ADOPTER_LOGO_URL',
] as const;

describe('getPlatformName', () => {
  afterEach(() => {
    applyRuntimeConfig(EMPTY_RUNTIME_CONFIG);
  });

  it('falls back to AI Switch when unset', () => {
    expect(getPlatformName()).toBe('AI Switch');
    expect(getPlatformName()).toBe(DEFAULT_PLATFORM_NAME);
  });

  it('returns the applied runtime config value', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      platformName: 'Custom Brand',
    });
    expect(getPlatformName()).toBe('Custom Brand');
  });

  it('falls back when the applied name is blank', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      platformName: '   ',
    });
    expect(getPlatformName()).toBe(DEFAULT_PLATFORM_NAME);
  });
});

describe('getAdopterLogoSrc', () => {
  afterEach(() => {
    applyRuntimeConfig(EMPTY_RUNTIME_CONFIG);
  });

  it('falls back to default SVG when unset', () => {
    expect(getAdopterLogoSrc()).toBe(DEFAULT_ADOPTER_LOGO_SRC);
  });

  it('uses ConfigMap URL when set', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: 'https://cdn.example.com/logo.png',
    });
    expect(getAdopterLogoSrc()).toBe('https://cdn.example.com/logo.png');
  });

  it('accepts http URLs', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: 'http://internal.example.com/logo.png',
    });
    expect(getAdopterLogoSrc()).toBe('http://internal.example.com/logo.png');
  });

  it('accepts same-origin paths', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: '/custom-logo.png',
    });
    expect(getAdopterLogoSrc()).toBe('/custom-logo.png');
  });

  it('rejects protocol-relative URLs', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: '//evil.com/x.png',
    });
    expect(getAdopterLogoSrc()).toBe(DEFAULT_ADOPTER_LOGO_SRC);
  });

  it('rejects javascript: URLs', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: 'javascript:alert(1)',
    });
    expect(getAdopterLogoSrc()).toBe(DEFAULT_ADOPTER_LOGO_SRC);
  });

  it('rejects data: URLs', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: 'data:image/svg+xml;base64,PHN2Zz4=',
    });
    expect(getAdopterLogoSrc()).toBe(DEFAULT_ADOPTER_LOGO_SRC);
  });

  it('rejects malformed URLs', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: 'not a url',
    });
    expect(getAdopterLogoSrc()).toBe(DEFAULT_ADOPTER_LOGO_SRC);
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

  it('reads ADOPTER_LOGO_URL', () => {
    process.env.ADOPTER_LOGO_URL = 'https://cdn.example.com/logo.png';
    expect(getServerRuntimeConfig().adopterLogoUrl).toBe(
      'https://cdn.example.com/logo.png',
    );
  });
});
