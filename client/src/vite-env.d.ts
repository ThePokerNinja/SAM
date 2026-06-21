/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK?: string;
  readonly VITE_LIVEKIT_URL?: string;
  readonly VITE_TOKEN_SERVER_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
