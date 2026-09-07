import {
  applyRuntimeConfig,
  DEFAULT_ADOPTER_LOGO_SRC,
  DEFAULT_PLATFORM_NAME,
  EMPTY_RUNTIME_CONFIG,
  getAdopterLogoSrc,
  getBranding,
  getPlatformName,
  getServerRuntimeConfig,
} from '../../src/config/runtimeConfig';
import {
  platformLogoSrcFromName,
  resolveAdopterLogoSrc,
  resolveEmailLogoUrl,
  resolvePlatformName,
} from '../../src/config/branding';

const ENV_KEYS = [
  'PLATFORM_NAME',
  'NEXT_PUBLIC_PLATFORM_NAME',
  'ADOPTER_LOGO_URL',
  'NEXT_PUBLIC_ADOPTER_LOGO_URL',
] as const;

describe('branding resolvers', () => {
  it('resolvePlatformName falls back to AI4I Orchestrate', () => {
    expect(resolvePlatformName('')).toBe(DEFAULT_PLATFORM_NAME);
    expect(resolvePlatformName('  ')).toBe(DEFAULT_PLATFORM_NAME);
    expect(resolvePlatformName('Custom Brand')).toBe('Custom Brand');
  });

  it('resolveAdopterLogoSrc accepts http(s) and same-origin paths only', () => {
    expect(resolveAdopterLogoSrc('')).toBe(DEFAULT_ADOPTER_LOGO_SRC);
    expect(resolveAdopterLogoSrc('/custom.png')).toBe('/custom.png');
    expect(resolveAdopterLogoSrc('https://cdn.example.com/a.png')).toBe(
      'https://cdn.example.com/a.png',
    );
    expect(resolveAdopterLogoSrc('//evil.com/x.png')).toBe(DEFAULT_ADOPTER_LOGO_SRC);
  });

  it('platformLogoSrcFromName maps safe PLATFORM_NAME folder slugs', () => {
    expect(platformLogoSrcFromName('AISWITCH')).toBe('/assests/AISWITCH/logo.png');
    expect(platformLogoSrcFromName('AI4I')).toBe('/assests/AI4I/logo.png');
    expect(platformLogoSrcFromName('../etc')).toBeNull();
    expect(platformLogoSrcFromName('a/b')).toBeNull();
    expect(platformLogoSrcFromName('')).toBeNull();
  });

  it('resolveEmailLogoUrl requires absolute http(s)', () => {
    expect(resolveEmailLogoUrl('/logo.png')).toBeNull();
    expect(resolveEmailLogoUrl('https://cdn.example.com/logo.png')).toBe(
      'https://cdn.example.com/logo.png',
    );
  });
});

describe('getPlatformName', () => {
  afterEach(() => {
    applyRuntimeConfig(EMPTY_RUNTIME_CONFIG);
  });

  it('falls back to AI4I Orchestrate when unset', () => {
    expect(getPlatformName()).toBe('AI4I Orchestrate');
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
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      platformName: 'AISWITCH',
    });
    expect(getAdopterLogoSrc()).toBe(DEFAULT_ADOPTER_LOGO_SRC);
  });

  it('uses ConfigMap URL when set', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      adopterLogoUrl: 'https://cdn.example.com/logo.png',
    });
    expect(getAdopterLogoSrc()).toBe('https://cdn.example.com/logo.png');
  });

  it('uses bundled /assests/<PLATFORM_NAME>/logo.png when ADOPTER_LOGO_URL is set to it', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      platformName: 'AISWITCH',
      adopterLogoUrl: '/assests/AISWITCH/logo.png',
    });
    expect(getAdopterLogoSrc()).toBe('/assests/AISWITCH/logo.png');
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

describe('getBranding', () => {
  afterEach(() => {
    applyRuntimeConfig(EMPTY_RUNTIME_CONFIG);
  });

  it('returns name and logo together', () => {
    applyRuntimeConfig({
      ...EMPTY_RUNTIME_CONFIG,
      platformName: 'AI4I Orchestrate',
      adopterLogoUrl: 'https://cdn.example.com/orch.png',
    });
    expect(getBranding()).toEqual({
      name: 'AI4I Orchestrate',
      logoSrc: 'https://cdn.example.com/orch.png',
    });
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

  it('falls back to AI4I Orchestrate when both env keys are empty', () => {
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
