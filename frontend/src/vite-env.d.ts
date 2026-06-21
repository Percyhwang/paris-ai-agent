/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_GOOGLE_CLIENT_ID?: string;
  readonly VITE_GOOGLE_ALLOWED_ORIGINS?: string;
  readonly VITE_GOOGLE_MAPS_API_KEY?: string;
  readonly VITE_HOME_BACKGROUND_URL?: string;
  readonly VITE_STATIC_DEMO_AUTH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  google?: {
    accounts: {
      id: {
        initialize: (options: {
          client_id: string;
          callback: (response: { credential?: string }) => void;
          ux_mode?: "popup" | "redirect";
          auto_select?: boolean;
          itp_support?: boolean;
        }) => void;
        renderButton: (element: HTMLElement, options: Record<string, unknown>) => void;
        prompt: () => void;
      };
    };
  };
}
