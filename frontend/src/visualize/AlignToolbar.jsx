/**
 * frontend/src/visualize/AlignToolbar.jsx
 * Floating toolbar that appears when multiple tiles (2+) are selected.
 * Provides Align Left/Right/Top/Bottom, Distribute H/V, and Group/Ungroup.
 */

import React from "react";
import { useDashboard } from "./dashboardContext";

export function AlignToolbar() {
  const { state, dispatch } = useDashboard();
  const { present } = state;
  const { selectedTileIds, mode, activePageId, pages } = present;

  if (mode !== "edit" || !selectedTileIds || selectedTileIds.length < 2) {
    return null;
  }

  const activePage = pages.find((p) => p.id === activePageId) || pages[0];
  const selectedTiles = (activePage?.tiles || []).filter((t) => selectedTileIds.includes(t.id));
  const isGrouped = selectedTiles.length > 0 && selectedTiles.every((t) => t.groupId && t.groupId === selectedTiles[0].groupId);

  const align = (alignment) => {
    dispatch({ type: "ALIGN_TILES", payload: { alignment } });
  };

  return (
    <div
      className="rpt-align-toolbar rpt-no-drag"
      style={{
        position: "absolute",
        top: 14,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 100,
        backgroundColor: "#18181b",
        border: "1px solid #3f3f46",
        borderRadius: 8,
        padding: "4px 8px",
        display: "flex",
        alignItems: "center",
        gap: 6,
        boxShadow: "0 8px 24px rgba(0, 0, 0, 0.5)",
      }}
    >
      <span style={{ fontSize: 11, fontWeight: 600, color: "#a1a1aa", marginRight: 4 }}>
        {selectedTileIds.length} Selected
      </span>

      {/* Align Left */}
      <button
        type="button"
        className="rpt-btn"
        style={{ fontSize: 11, padding: "3px 6px" }}
        onClick={() => align("left")}
        title="Align Left"
      >
        ⇤ Left
      </button>

      {/* Align Right */}
      <button
        type="button"
        className="rpt-btn"
        style={{ fontSize: 11, padding: "3px 6px" }}
        onClick={() => align("right")}
        title="Align Right"
      >
        ⇥ Right
      </button>

      {/* Align Top */}
      <button
        type="button"
        className="rpt-btn"
        style={{ fontSize: 11, padding: "3px 6px" }}
        onClick={() => align("top")}
        title="Align Top"
      >
        ⤒ Top
      </button>

      {/* Align Bottom */}
      <button
        type="button"
        className="rpt-btn"
        style={{ fontSize: 11, padding: "3px 6px" }}
        onClick={() => align("bottom")}
        title="Align Bottom"
      >
        ⤓ Bottom
      </button>

      {/* Distribute H */}
      <button
        type="button"
        className="rpt-btn"
        style={{ fontSize: 11, padding: "3px 6px" }}
        onClick={() => align("distributeH")}
        title="Distribute Horizontally"
      >
        ↔ Space H
      </button>

      {/* Distribute V */}
      <button
        type="button"
        className="rpt-btn"
        style={{ fontSize: 11, padding: "3px 6px" }}
        onClick={() => align("distributeV")}
        title="Distribute Vertically"
      >
        ↕ Space V
      </button>

      {/* Group / Ungroup */}
      {isGrouped ? (
        <button
          type="button"
          className="rpt-btn"
          style={{ fontSize: 11, padding: "3px 8px", color: "#f87171" }}
          onClick={() => dispatch({ type: "UNGROUP_TILES" })}
          title="Ungroup selected visuals"
        >
          ⛓️‍💥 Ungroup
        </button>
      ) : (
        <button
          type="button"
          className="rpt-btn rpt-btn-primary"
          style={{ fontSize: 11, padding: "3px 8px" }}
          onClick={() => dispatch({ type: "GROUP_TILES" })}
          title="Group selected visuals to move together"
        >
          🔗 Group
        </button>
      )}

      {/* Clear selection */}
      <button
        type="button"
        className="rpt-hover-icon-btn"
        onClick={() => dispatch({ type: "CLEAR_SELECTION" })}
        title="Clear Selection"
      >
        ✕
      </button>
    </div>
  );
}
