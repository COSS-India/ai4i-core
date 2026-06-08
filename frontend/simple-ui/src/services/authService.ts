/**
 * Authentication service — domain modules composed for backward-compatible API.
 */

import * as apiKeys from "./auth/apiKeys";
import * as login from "./auth/login";
import * as session from "./auth/session";
import * as users from "./auth/users";

export const authService = {
  // Session & tokens
  getAccessToken: session.getAccessToken,
  setAccessToken: session.setAccessToken,
  getRefreshToken: session.getRefreshToken,
  setRefreshToken: session.setRefreshToken,
  clearAuthTokens: session.clearAuthTokens,
  isAuthenticated: session.isAuthenticated,
  getStoredUser: session.getStoredUser,
  setStoredUser: session.setStoredUser,
  clearStoredUser: session.clearStoredUser,
  getTokenExpiry: session.getTokenExpiry,
  isTokenExpired: session.isTokenExpired,
  isTokenExpiringSoon: session.isTokenExpiringSoon,
  getTimeUntilExpiry: session.getTimeUntilExpiry,
  getLoginTimestamp: session.getLoginTimestamp,
  isSessionExpired: session.isSessionExpired,
  getTimeUntilSessionExpiry: session.getTimeUntilSessionExpiry,
  refreshToken: session.refreshToken,
  validateToken: session.validateToken,
  getCurrentUser: session.getCurrentUser,
  updateCurrentUser: session.updateCurrentUser,
  changePassword: session.changePassword,
  refreshIfExpiringSoon: session.refreshIfExpiringSoon,
  ensureValidToken: session.ensureValidToken,

  // Login & registration
  register: login.register,
  login: login.login,
  guestLogin: login.guestLogin,
  getGuestEnabledServices: login.getGuestEnabledServices,
  logout: login.logout,
  requestPasswordReset: login.requestPasswordReset,
  resetPassword: login.resetPassword,
  getSetPasswordStatus: login.getSetPasswordStatus,
  setPasswordWithToken: login.setPasswordWithToken,
  verifyEmail: login.verifyEmail,
  resendVerification: login.resendVerification,
  resendSetupLink: login.resendSetupLink,
  getOAuth2Providers: login.getOAuth2Providers,
  exchangeOAuthCode: login.exchangeOAuthCode,
  checkEmailExists: login.checkEmailExists,

  // API keys
  createApiKey: apiKeys.createApiKey,
  createApiKeyForUser: apiKeys.createApiKeyForUser,
  listApiKeys: apiKeys.listApiKeys,
  listAllApiKeys: apiKeys.listAllApiKeys,
  revokeApiKey: apiKeys.revokeApiKey,
  revokeApiKeyRecord: apiKeys.revokeApiKeyRecord,
  updateApiKey: apiKeys.updateApiKey,

  // Users & permissions
  getAllUsers: users.getAllUsers,
  listUsersPage: users.listUsersPage,
  getUserById: users.getUserById,
  getAllPermissions: users.getAllPermissions,
};

export default authService;
