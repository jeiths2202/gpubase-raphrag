/// <reference types="vite/client" />

// Node.js global types for test files
declare const global: typeof globalThis;
declare const process: {
  env: {
    NODE_ENV: string;
    VISUAL_REGRESSION?: string;
    [key: string]: string | undefined;
  };
};

// Vite environment variables
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_GOOGLE_CLIENT_ID: string;
  readonly VITE_SSO_PROVIDER_URL: string;
  readonly MODE: string;
  readonly DEV: boolean;
  readonly PROD: boolean;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
