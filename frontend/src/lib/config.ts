// src/lib/config.ts
export function resolveCompanyCode(): string | null {
    if (typeof window === "undefined") return null;
    try {
      const url = new URL(window.location.href);
      const val = url.searchParams.get("companyCode") || url.searchParams.get("company_code");
      return val && val.trim() ? val.trim() : null;
    } catch (_) {
      return null;
    }
  }
  
  export function resolveUsername(): string | null {
    if (typeof window === "undefined") return null;
    try {
      const url = new URL(window.location.href);
      const val = url.searchParams.get("username") || url.searchParams.get("user");
      return val && val.trim() ? val.trim() : null;
    } catch (_) {
      return null;
    }
  }