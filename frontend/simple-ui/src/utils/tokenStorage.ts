/**
 * Encrypted token storage for access_token and refresh_token.
 * Tokens are encrypted at rest using AES and decrypted when read.
 * Set NEXT_PUBLIC_TOKEN_ENCRYPTION_KEY (min 16 chars) in env for production.
 */

import CryptoJS from 'crypto-js';

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const REMEMBER_ME_KEY = 'remember_me';
const ENCRYPTED_PREFIX = 'enc:';

/** Keys that must never hold auth/session data in localStorage (legacy cleanup). */
const LEGACY_LOCAL_AUTH_KEYS = [
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  REMEMBER_ME_KEY,
  'login_timestamp',
  'user',
] as const;

function purgeLegacyAuthLocalStorage(): void {
  if (typeof window === 'undefined') return;
  try {
    for (const k of LEGACY_LOCAL_AUTH_KEYS) {
      localStorage.removeItem(k);
    }
  } catch {
    // private mode / blocked storage
  }
}

/**
 * Whether "remember me" was chosen for this browser session (sessionStorage only).
 */
export function getRememberMeFromStorage(): boolean {
  if (typeof window === 'undefined') return false;
  return sessionStorage.getItem(REMEMBER_ME_KEY) === 'true';
}

function getEncryptionKey(): string {
  const key = typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_TOKEN_ENCRYPTION_KEY;
  if (key && key.length >= 16) return key;
  // Fallback for dev when env not set (still encrypts, but use a fixed salt for consistency)
  return 'ai4i-token-storage-v1';
}

function encrypt(plainText: string): string {
  try {
    const key = getEncryptionKey();
    const ciphertext = CryptoJS.AES.encrypt(plainText, key).toString();
    return ENCRYPTED_PREFIX + ciphertext;
  } catch (e) {
    console.error('Token encryption failed:', e);
    return plainText;
  }
}

function decrypt(value: string): string | null {
  if (!value || value.trim() === '') return null;
  if (!value.startsWith(ENCRYPTED_PREFIX)) {
    return value.trim();
  }
  try {
    const key = getEncryptionKey();
    const ciphertext = value.slice(ENCRYPTED_PREFIX.length);
    const bytes = CryptoJS.AES.decrypt(ciphertext, key);
    const plain = bytes.toString(CryptoJS.enc.Utf8);
    return plain || null;
  } catch (e) {
    console.error('Token decryption failed:', e);
    return null;
  }
}

function getRawFromStorage(key: string): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem(key);
}

/**
 * Get decrypted access token from storage.
 */
export function getStoredAccessToken(): string | null {
  const raw = getRawFromStorage(ACCESS_TOKEN_KEY);
  if (!raw) return null;
  const decrypted = decrypt(raw);
  return decrypted && decrypted.trim() !== '' ? decrypted.trim() : null;
}

/**
 * Get decrypted refresh token from storage.
 */
export function getStoredRefreshToken(): string | null {
  const raw = getRawFromStorage(REFRESH_TOKEN_KEY);
  if (!raw) return null;
  const decrypted = decrypt(raw);
  return decrypted && decrypted.trim() !== '' ? decrypted.trim() : null;
}

/**
 * Encrypt and store access token.
 */
export function setStoredAccessToken(token: string, rememberMe: boolean): void {
  if (typeof window === 'undefined') return;
  purgeLegacyAuthLocalStorage();
  sessionStorage.setItem(REMEMBER_ME_KEY, rememberMe ? 'true' : 'false');
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  const encrypted = encrypt(token);
  sessionStorage.setItem(ACCESS_TOKEN_KEY, encrypted);
}

/**
 * Encrypt and store refresh token.
 */
export function setStoredRefreshToken(token: string, rememberMe: boolean): void {
  if (typeof window === 'undefined') return;
  purgeLegacyAuthLocalStorage();
  sessionStorage.setItem(REMEMBER_ME_KEY, rememberMe ? 'true' : 'false');
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  const encrypted = encrypt(token);
  sessionStorage.setItem(REFRESH_TOKEN_KEY, encrypted);
}

/**
 * Remove auth keys from sessionStorage and strip any legacy localStorage copies.
 */
export function clearTokenStorage(): void {
  if (typeof window === 'undefined') return;
  purgeLegacyAuthLocalStorage();
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
  sessionStorage.removeItem(REMEMBER_ME_KEY);
  sessionStorage.removeItem('login_timestamp');
  sessionStorage.removeItem('user');
}
