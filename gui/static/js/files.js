/* File-type helpers shared by the details pane and the media browser. */

import { esc } from "./util.js";
import { extIcon } from "./icons.js";

export const IMG_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);
export const isImg = (name) => IMG_EXTS.has((name || "").split(".").pop().toLowerCase());
// v2 file records are {id, name, bytes, sha256} — the id is the sealed blob
// id; the serving endpoint speaks ?chat=&id= (the v1 ?id=<chat>&path= spelling
// broke every attachment click after the cutover)
export const fileUrl = (chatId, fileId) =>
  `/api/mesh/file?chat=${encodeURIComponent(chatId)}&id=${encodeURIComponent(fileId)}`;

export function mediaThumb(chatId, f) {
  return isImg(f.name)
    ? `<span class="media-tile"><img src="${fileUrl(chatId, f.id)}" alt="" loading="lazy"></span>`
    : `<span class="media-tile file"><span style="font-size:19px">${extIcon(f.name)}</span>
       <span class="mt-ext">${esc((f.name.split(".").pop() || "").toUpperCase().slice(0, 5))}</span></span>`;
}

export function monthLabel(ts) {
  const d = new Date(ts), now = new Date();
  if (isNaN(d)) return "";
  if (d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth()) {
    return "This month";
  }
  const m = d.toLocaleDateString([], { month: "long" });
  return d.getFullYear() === now.getFullYear() ? m : `${m} ${d.getFullYear()}`;
}
