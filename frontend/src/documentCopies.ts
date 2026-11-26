import type { SessionContext } from "./sessionContext.ts";

export type CopyRecord = {
  id: string;
  title: string;
  filename: string;
  language: string;
  version: number;
  updated: number;
};
export type CopyReview = {
  items: CopyRecord[];
  visible_count: number;
  offset: number;
  next_offset: number | null;
};

// Bind the preview to both the displayed version and the captured account/context.
export function checkedCopies(
  value: any,
  context: SessionContext | null,
  id: string,
  version: number,
  offset: number,
): CopyReview {
  if (
    !context ||
    value?.scope?.workspace_id !== context.workspace_id ||
    value?.scope?.account_id !== context.user_id ||
    value?.scope?.environment !== context.environment ||
    value?.source?.id !== id ||
    value?.source?.version !== version ||
    value?.offset !== offset ||
    !Number.isSafeInteger(value?.visible_count) ||
    value.visible_count < 0 ||
    value.visible_count > 199 ||
    !Array.isArray(value?.items) ||
    value.items.length > 20 ||
    value.items.length !==
      Math.min(20, Math.max(0, value.visible_count - offset)) ||
    value.next_offset !==
      (value.visible_count > offset + 20 ? offset + 20 : null) ||
    value.items.some(
      (item: any) =>
        !item ||
        typeof item.id !== "string" ||
        !item.id ||
        item.id === id ||
        ![item.title, item.filename, item.language].every(
          (v) => typeof v === "string",
        ) ||
        !Number.isFinite(item.updated) ||
        !Number.isSafeInteger(item.version) ||
        item.version < 1,
    ) ||
    new Set(value.items.map((item: CopyRecord) => item.id)).size !==
      value.items.length
  )
    throw new Error(
      "The copy review no longer matches this source and workspace. Refresh the source and try again.",
    );
  return value;
}
