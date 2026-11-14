/**
 * frontend/src/visualize/dashboardReducer.js
 * State reducer with undo/redo history stack for the Dashboard Builder.
 */

import { makePageId, makeTileId, makeEmptyPage, clampTilePx, createDefaultTile } from "./utils";

const MAX_HISTORY = 30;

// Actions that do NOT record history
const NON_HISTORY_ACTIONS = new Set([
  "SET_ACTIVE_PAGE",
  "SELECT_TILE",
  "CLEAR_SELECTION",
  "SET_MODE",
  "COPY_TILES",
  "SET_CROSS_FILTER",
  "CLEAR_CROSS_FILTER",
  "UNDO",
  "REDO",
  "LOAD_SAVED_STATE",
]);

function pushHistory(state, newPresent) {
  return {
    past: [...state.past.slice(-(MAX_HISTORY - 1)), state.present],
    present: newPresent,
    future: [],
  };
}

export function createInitialState(initialDashboard) {
  return {
    past: [],
    present: initialDashboard,
    future: [],
  };
}

export function dashboardReducer(state, action) {
  const { present } = state;
  const activePage = present.pages.find((p) => p.id === present.activePageId) || present.pages[0];

  const updateActivePage = (updater) => {
    const newPages = present.pages.map((p) => (p.id === activePage.id ? updater(p) : p));
    return { ...present, pages: newPages };
  };

  switch (action.type) {
    case "UNDO": {
      if (state.past.length === 0) return state;
      const previous = state.past[state.past.length - 1];
      const newPast = state.past.slice(0, state.past.length - 1);
      return {
        past: newPast,
        present: { ...previous, selectedTileIds: [] },
        future: [present, ...state.future],
      };
    }

    case "REDO": {
      if (state.future.length === 0) return state;
      const next = state.future[0];
      const newFuture = state.future.slice(1);
      return {
        past: [...state.past, present],
        present: { ...next, selectedTileIds: [] },
        future: newFuture,
      };
    }

    case "LOAD_SAVED_STATE": {
      return {
        past: [],
        present: { ...action.payload, mode: "edit", selectedTileIds: [] },
        future: [],
      };
    }

    case "SET_MODE": {
      return {
        ...state,
        present: { ...present, mode: action.payload, selectedTileIds: [] },
      };
    }

    case "SET_SETTINGS": {
      const newPresent = { ...present, settings: { ...present.settings, ...action.payload } };
      return pushHistory(state, newPresent);
    }

    case "SET_DASHBOARD_NAME": {
      const newPresent = { ...present, name: action.payload };
      return pushHistory(state, newPresent);
    }

    case "SET_ACTIVE_PAGE": {
      return {
        ...state,
        present: { ...present, activePageId: action.payload, selectedTileIds: [] },
      };
    }

    case "ADD_PAGE": {
      const newPage = makeEmptyPage(action.payload?.name || `Page ${present.pages.length + 1}`);
      const newPresent = {
        ...present,
        pages: [...present.pages, newPage],
        activePageId: newPage.id,
        selectedTileIds: [],
      };
      return pushHistory(state, newPresent);
    }

    case "ADD_GENERATED_PAGE": {
      const newPage = action.payload;
      const newPresent = {
        ...present,
        pages: [...present.pages, newPage],
        activePageId: newPage.id,
        selectedTileIds: [],
      };
      return pushHistory(state, newPresent);
    }

    case "RENAME_PAGE": {
      const { id, name } = action.payload;
      const newPages = present.pages.map((p) => (p.id === id ? { ...p, name } : p));
      return pushHistory(state, { ...present, pages: newPages });
    }

    case "DUPLICATE_PAGE": {
      const { pageId } = action.payload;
      const source = present.pages.find((p) => p.id === pageId) || activePage;
      const idMap = new Map();
      const newTiles = source.tiles.map((t) => {
        const newId = makeTileId(t.kind);
        idMap.set(t.id, newId);
        return { ...JSON.parse(JSON.stringify(t)), id: newId };
      });
      // update groupIds in duplicated page
      newTiles.forEach((t) => {
        if (t.groupId && idMap.has(t.groupId)) {
          t.groupId = idMap.get(t.groupId);
        }
      });
      const duplicatedPage = {
        ...JSON.parse(JSON.stringify(source)),
        id: makePageId(),
        name: `${source.name} (Copy)`,
        tiles: newTiles,
      };
      const newPages = [...present.pages, duplicatedPage];
      return pushHistory(state, {
        ...present,
        pages: newPages,
        activePageId: duplicatedPage.id,
        selectedTileIds: [],
      });
    }

    case "DELETE_PAGE": {
      if (present.pages.length <= 1) return state;
      const { pageId } = action.payload;
      const newPages = present.pages.filter((p) => p.id !== pageId);
      const newActive = newPages.some((p) => p.id === present.activePageId)
        ? present.activePageId
        : newPages[0].id;
      return pushHistory(state, {
        ...present,
        pages: newPages,
        activePageId: newActive,
        selectedTileIds: [],
      });
    }

    case "TOGGLE_HIDE_PAGE": {
      const { pageId } = action.payload;
      const newPages = present.pages.map((p) =>
        p.id === pageId ? { ...p, hidden: !p.hidden } : p
      );
      return pushHistory(state, { ...present, pages: newPages });
    }

    case "REORDER_PAGES": {
      const { sourceIndex, destIndex } = action.payload;
      if (sourceIndex === destIndex) return state;
      const pages = [...present.pages];
      const [removed] = pages.splice(sourceIndex, 1);
      pages.splice(destIndex, 0, removed);
      return pushHistory(state, { ...present, pages });
    }

    case "SELECT_TILE": {
      const { tileId, multi } = action.payload;
      let newSelected;
      if (!tileId) {
        newSelected = [];
      } else if (multi) {
        newSelected = present.selectedTileIds.includes(tileId)
          ? present.selectedTileIds.filter((id) => id !== tileId)
          : [...present.selectedTileIds, tileId];
      } else {
        newSelected = [tileId];
      }
      return {
        ...state,
        present: { ...present, selectedTileIds: newSelected },
      };
    }

    case "CLEAR_SELECTION": {
      return {
        ...state,
        present: { ...present, selectedTileIds: [] },
      };
    }

    case "ADD_TILE": {
      const tile = action.payload;
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: [...page.tiles, tile],
      }));
      return pushHistory(state, { ...newPresent, selectedTileIds: [tile.id] });
    }

    case "UPDATE_TILE": {
      const { tileId, updates } = action.payload;
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: page.tiles.map((t) => (t.id === tileId ? { ...t, ...updates } : t)),
      }));
      return pushHistory(state, newPresent);
    }

    case "UPDATE_TILE_LAYOUT": {
      const { tileId, x, y, w, h } = action.payload;
      const target = activePage.tiles.find((t) => t.id === tileId);
      if (!target) return state;
      const dx = x - target.x;
      const dy = y - target.y;
      const clamped = clampTilePx(x, y, w, h);

      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: page.tiles.map((t) => {
          if (t.id === tileId) {
            return { ...t, ...clamped };
          }
          if (target.groupId && t.groupId === target.groupId && w === target.w && h === target.h) {
            const shifted = clampTilePx(t.x + dx, t.y + dy, t.w, t.h);
            return { ...t, ...shifted };
          }
          return t;
        }),
      }));
      return pushHistory(state, newPresent);
    }

    case "DELETE_TILES": {
      const targetIds = action.payload?.tileIds || present.selectedTileIds;
      if (!targetIds || targetIds.length === 0) return state;
      const targetSet = new Set(targetIds);
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: page.tiles.filter((t) => !targetSet.has(t.id)),
      }));
      return pushHistory(state, { ...newPresent, selectedTileIds: [] });
    }

    case "COPY_TILES": {
      const targetIds = action.payload?.tileIds || present.selectedTileIds;
      let tilesToCopy = activePage.tiles.filter((t) => targetIds.includes(t.id));
      if (tilesToCopy.length === 0 && activePage.tiles.length === 1) {
        tilesToCopy = activePage.tiles;
      }
      if (tilesToCopy.length === 0) return state;
      return {
        ...state,
        present: {
          ...present,
          clipboard: JSON.parse(JSON.stringify(tilesToCopy)),
        },
      };
    }

    case "PASTE_TILES": {
      if (!present.clipboard || present.clipboard.length === 0) return state;
      const offset = 20;
      const idMap = new Map();
      const newTiles = present.clipboard.map((t) => {
        const newId = makeTileId(t.kind);
        idMap.set(t.id, newId);
        const clamped = clampTilePx(t.x + offset, t.y + offset, t.w, t.h);
        return {
          ...JSON.parse(JSON.stringify(t)),
          id: newId,
          ...clamped,
        };
      });
      newTiles.forEach((t) => {
        if (t.groupId && idMap.has(t.groupId)) {
          t.groupId = idMap.get(t.groupId);
        }
      });
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: [...page.tiles, ...newTiles],
      }));
      return pushHistory(state, {
        ...newPresent,
        selectedTileIds: newTiles.map((t) => t.id),
      });
    }

    case "DUPLICATE_TILES": {
      const targetIds = action.payload?.tileIds || present.selectedTileIds;
      const tilesToDup = activePage.tiles.filter((t) => targetIds.includes(t.id));
      if (tilesToDup.length === 0) return state;
      const offset = 20;
      const newTiles = tilesToDup.map((t) => {
        const clamped = clampTilePx(t.x + offset, t.y + offset, t.w, t.h);
        return {
          ...JSON.parse(JSON.stringify(t)),
          id: makeTileId(t.kind),
          ...clamped,
          groupId: null,
        };
      });
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: [...page.tiles, ...newTiles],
      }));
      return pushHistory(state, {
        ...newPresent,
        selectedTileIds: newTiles.map((t) => t.id),
      });
    }

    case "BRING_TO_FRONT": {
      const tileId = action.payload?.tileId || present.selectedTileIds[0];
      if (!tileId) return state;
      const maxZ = Math.max(0, ...activePage.tiles.map((t) => t.z || 1));
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: page.tiles.map((t) => (t.id === tileId ? { ...t, z: maxZ + 1 } : t)),
      }));
      return pushHistory(state, newPresent);
    }

    case "SEND_TO_BACK": {
      const tileId = action.payload?.tileId || present.selectedTileIds[0];
      if (!tileId) return state;
      const minZ = Math.min(1, ...activePage.tiles.map((t) => t.z || 1));
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: page.tiles.map((t) => (t.id === tileId ? { ...t, z: Math.max(0, minZ - 1) } : t)),
      }));
      return pushHistory(state, newPresent);
    }

    case "GROUP_TILES": {
      const targetIds = action.payload?.tileIds || present.selectedTileIds;
      if (!targetIds || targetIds.length < 2) return state;
      const newGroupId = `grp-${Date.now()}`;
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: page.tiles.map((t) =>
          targetIds.includes(t.id) ? { ...t, groupId: newGroupId } : t
        ),
      }));
      return pushHistory(state, newPresent);
    }

    case "UNGROUP_TILES": {
      const targetIds = action.payload?.tileIds || present.selectedTileIds;
      if (!targetIds || targetIds.length === 0) return state;
      const newPresent = updateActivePage((page) => ({
        ...page,
        tiles: page.tiles.map((t) =>
          targetIds.includes(t.id) ? { ...t, groupId: null } : t
        ),
      }));
      return pushHistory(state, newPresent);
    }

    case "ALIGN_TILES": {
      const { alignment } = action.payload;
      const targetIds = present.selectedTileIds;
      if (!targetIds || targetIds.length < 2) return state;
      const selectedTiles = activePage.tiles.filter((t) => targetIds.includes(t.id));
      if (selectedTiles.length < 2) return state;

      let newPresent;
      if (alignment === "left") {
        const minX = Math.min(...selectedTiles.map((t) => t.x));
        newPresent = updateActivePage((page) => ({
          ...page,
          tiles: page.tiles.map((t) => (targetIds.includes(t.id) ? { ...t, x: minX } : t)),
        }));
      } else if (alignment === "right") {
        const maxR = Math.max(...selectedTiles.map((t) => t.x + t.w));
        newPresent = updateActivePage((page) => ({
          ...page,
          tiles: page.tiles.map((t) => (targetIds.includes(t.id) ? { ...t, x: maxR - t.w } : t)),
        }));
      } else if (alignment === "top") {
        const minY = Math.min(...selectedTiles.map((t) => t.y));
        newPresent = updateActivePage((page) => ({
          ...page,
          tiles: page.tiles.map((t) => (targetIds.includes(t.id) ? { ...t, y: minY } : t)),
        }));
      } else if (alignment === "bottom") {
        const maxB = Math.max(...selectedTiles.map((t) => t.y + t.h));
        newPresent = updateActivePage((page) => ({
          ...page,
          tiles: page.tiles.map((t) => (targetIds.includes(t.id) ? { ...t, y: maxB - t.h } : t)),
        }));
      } else if (alignment === "distributeH") {
        const sorted = [...selectedTiles].sort((a, b) => a.x - b.x);
        const minX = sorted[0].x;
        const maxX = sorted[sorted.length - 1].x;
        const totalSpan = maxX - minX;
        const step = totalSpan / (sorted.length - 1);
        const idToX = new Map();
        sorted.forEach((t, idx) => idToX.set(t.id, Math.round(minX + idx * step)));
        newPresent = updateActivePage((page) => ({
          ...page,
          tiles: page.tiles.map((t) => (idToX.has(t.id) ? { ...t, x: idToX.get(t.id) } : t)),
        }));
      } else if (alignment === "distributeV") {
        const sorted = [...selectedTiles].sort((a, b) => a.y - b.y);
        const minY = sorted[0].y;
        const maxY = sorted[sorted.length - 1].y;
        const totalSpan = maxY - minY;
        const step = totalSpan / (sorted.length - 1);
        const idToY = new Map();
        sorted.forEach((t, idx) => idToY.set(t.id, Math.round(minY + idx * step)));
        newPresent = updateActivePage((page) => ({
          ...page,
          tiles: page.tiles.map((t) => (idToY.has(t.id) ? { ...t, y: idToY.get(t.id) } : t)),
        }));
      }
      return newPresent ? pushHistory(state, newPresent) : state;
    }

    case "SET_PAGE_FILTER": {
      const { col, values } = action.payload;
      const newPresent = updateActivePage((page) => {
        const existing = (page.filters || []).filter((f) => f.col !== col);
        const filters = values && values.length > 0 ? [...existing, { col, values }] : existing;
        return { ...page, filters };
      });
      return pushHistory(state, newPresent);
    }

    case "CLEAR_PAGE_FILTER": {
      const { col } = action.payload;
      const newPresent = updateActivePage((page) => ({
        ...page,
        filters: (page.filters || []).filter((f) => f.col !== col),
      }));
      return pushHistory(state, newPresent);
    }

    case "SET_CROSS_FILTER": {
      const { col, value, sourceTileId } = action.payload;
      const newPages = present.pages.map((p) =>
        p.id === activePage.id ? { ...p, crossFilter: { col, value, sourceTileId } } : p
      );
      return { ...state, present: { ...present, pages: newPages } };
    }

    case "CLEAR_CROSS_FILTER": {
      const newPages = present.pages.map((p) =>
        p.id === activePage.id ? { ...p, crossFilter: null } : p
      );
      return { ...state, present: { ...present, pages: newPages } };
    }

    default:
      return state;
  }
}
