export type Tokens = {
  access_token: string;
  refresh_token?: string;
};

const ACCESS_TOKEN_KEY = "nb_access_token";
const REFRESH_TOKEN_KEY = "nb_refresh_token";

export function getAccessToken(): string {
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setTokens(tokens: Tokens): void {
  try {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    if (tokens.refresh_token) {
      window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    }
  } catch {
    // ignore
  }
}

export function clearTokens(): void {
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // ignore
  }
}
