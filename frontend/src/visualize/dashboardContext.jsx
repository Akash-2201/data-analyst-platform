/**
 * frontend/src/visualize/dashboardContext.js
 * React context for dashboard state, dispatch, active page, and selection.
 */

import React, { createContext, useContext, useMemo } from "react";

const DashboardContext = createContext(null);

export function DashboardProvider({ value, children }) {
  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard() {
  const context = useContext(DashboardContext);
  if (!context) {
    throw new Error("useDashboard must be used within a DashboardProvider");
  }
  return context;
}
