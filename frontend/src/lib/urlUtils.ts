/**
 * Get query parameters from URL
 * @returns Object containing all query parameters
 */
export const getQueryParams = (): Record<string, string> => {
  if (typeof window === 'undefined') return {};
  
  const params = new URLSearchParams(window.location.search);
  const paramsObj: Record<string, string> = {};
  
  for (const [key, value] of params.entries()) {
    paramsObj[key] = value;
  }
  
  return paramsObj;
};

/**
 * Get a specific query parameter value
 * @param paramName - Name of the query parameter
 * @returns Value of the query parameter or null if not found
 */
export const getQueryParam = (paramName: string): string | null => {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get(paramName);
};

import { useState, useEffect } from 'react';

/**
 * Hook to get query parameters in React components
 * @returns Object containing all query parameters
 */
export const useQueryParams = (): Record<string, string> => {
  if (typeof window === 'undefined') return {};
  
  const [params, setParams] = useState<Record<string, string>>({});
  
  useEffect(() => {
    const updateParams = () => {
      setParams(getQueryParams());
    };
    
    // Initial load
    updateParams();
    
    // Listen for URL changes
    window.addEventListener('popstate', updateParams);
    
    return () => {
      window.removeEventListener('popstate', updateParams);
    };
  }, []);
  
  return params;
};
