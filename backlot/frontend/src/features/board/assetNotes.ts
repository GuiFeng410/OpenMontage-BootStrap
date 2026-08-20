export const ASSET_NOTES_VERSION = "1.0";
export const ASSET_NOTES_PREFIX = "backlot.asset-notes.v1";
export const ASSET_NOTES_EVENT = "backlot:asset-notes-changed";
export const PREFER_OPTION_EVENT = "backlot:prefer-decision-option";

export type AssetNoteKind = "user" | "ai" | "reuse" | "skip";
export type AssetNoteAction = "" | "reject" | "redo" | "ok";

export type AssetNoteItem = {
  kind: AssetNoteKind;
  beat?: string;
  path?: string;
  label?: string;
  action: AssetNoteAction;
  text: string;
};

export type AssetNoteStore = {
  version: string;
  project_id: string;
  stage: string;
  items: Record<string, AssetNoteItem>;
};

export type NoteStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

function storageKey(projectId: string, stage: string) {
  return `${ASSET_NOTES_PREFIX}:${projectId}:${stage}`;
}

export function assetNoteKey(kind: AssetNoteKind, beat?: string, path?: string) {
  return `${kind}:${beat || "-"}:${path || "-"}`;
}

export function emptyAssetNotes(projectId: string, stage: string): AssetNoteStore {
  return { version: ASSET_NOTES_VERSION, project_id: projectId, stage, items: {} };
}

export function loadAssetNotes(
  storage: NoteStorage,
  projectId: string,
  stage: string,
): AssetNoteStore {
  try {
    const raw = storage.getItem(storageKey(projectId, stage));
    if (!raw) return emptyAssetNotes(projectId, stage);
    const parsed = JSON.parse(raw) as AssetNoteStore;
    if (
      !parsed ||
      parsed.version !== ASSET_NOTES_VERSION ||
      parsed.project_id !== projectId ||
      parsed.stage !== stage ||
      !parsed.items ||
      typeof parsed.items !== "object"
    ) {
      return emptyAssetNotes(projectId, stage);
    }
    return parsed;
  } catch {
    return emptyAssetNotes(projectId, stage);
  }
}

export function saveAssetNotes(storage: NoteStorage, store: AssetNoteStore) {
  try {
    storage.setItem(storageKey(store.project_id, store.stage), JSON.stringify(store));
  } catch {
    // Session-scoped persistence is best-effort.
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(ASSET_NOTES_EVENT));
  }
}

export function upsertAssetNote(
  store: AssetNoteStore,
  key: string,
  patch: Partial<AssetNoteItem> & Pick<AssetNoteItem, "kind">,
): AssetNoteStore {
  const prev = store.items[key] || {
    kind: patch.kind,
    beat: patch.beat,
    path: patch.path,
    label: patch.label,
    action: "" as AssetNoteAction,
    text: "",
  };
  const next: AssetNoteItem = {
    ...prev,
    ...patch,
    action: (patch.action ?? prev.action ?? "") as AssetNoteAction,
    text: String(patch.text ?? prev.text ?? ""),
  };
  const empty = !next.action && !String(next.text || "").trim();
  const items = { ...store.items };
  if (empty) delete items[key];
  else items[key] = next;
  return { ...store, items };
}

export function composeAssetNotes(store: AssetNoteStore) {
  const lines: string[] = [];
  for (const item of Object.values(store.items || {})) {
    const bits: string[] = [];
    if (item.label) bits.push(item.label);
    else if (item.beat) bits.push(item.beat);
    else if (item.path) bits.push(item.path);
    if (item.action === "reject") bits.push("这张不好");
    if (item.action === "redo") bits.push("请重做");
    if (item.action === "ok") bits.push("可以通过");
    const text = String(item.text || "").trim();
    if (text) bits.push(text);
    if (bits.length) lines.push(bits.join("："));
  }
  if (!lines.length) return "";
  return `【按图意见】\n${lines.join("\n")}`;
}

export function mergeIntentNote(globalNote: string, assetBlock: string) {
  const parts = [String(globalNote || "").trim(), String(assetBlock || "").trim()].filter(Boolean);
  return parts.join("\n");
}

export function preferDecisionOption(optionId: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(PREFER_OPTION_EVENT, { detail: { optionId } }),
  );
}
