// src/lib/iframeContext.ts
// Utility functions to read company code and username from iframe query parameters
// For production, you can use these to pre-fill or override input fields.
//
// Usage Example:
// import { resolveCompanyCode, resolveCtxUser } from "@/lib/iframeContext";
// const iframeCompanyCode = resolveCompanyCode();
// const iframeUsername = resolveCtxUser();
//
// // Use as default values for your input fields:
// // const [sqlCompanyCode, setSqlCompanyCode] = useState(iframeCompanyCode || "");
// // const [sqlUsername, setSqlUsername] = useState(iframeUsername || "");
//
// To enable, uncomment the usage in your page/component.

export function resolveCompanyCode(): string | null {
    if (typeof window === "undefined") return null;
    try {
      const url = new URL(window.location.href);
      const val = url.searchParams.get("companycode") || url.searchParams.get("CompanyCode");
      return val && val.trim() ? val.trim() : null;
    } catch (_) {
      return null;
    }
  }
  
  export function resolveCtxUser(): string | null {
    if (typeof window === "undefined") return null;
    try {
      const url = new URL(window.location.href);
      const val = url.searchParams.get("Ctxuser") || url.searchParams.get("ctxuser");
      return val && val.trim() ? val.trim() : null;
    } catch (_) {
      return null;
    }
  }