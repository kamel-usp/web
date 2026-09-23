/**
 * Icon geometry, on a 24×24 grid.
 *
 * Written here rather than pulled from an icon package: the editor needs six
 * glyphs, all of them generic shapes, and `flowbite-svelte-icons` was a
 * dependency that pinned Svelte 4 and so blocked the framework upgrade. Six
 * path strings are cheaper to own than a package to track.
 *
 * Solid paths (`FILE`, `UPLOAD`, `DOWNLOAD`) are filled; the rest are stroked
 * with `Icon.svelte`'s default settings.
 */

/** A sheet of paper with a folded corner: a program, or anything unknown. Solid. */
export const FILE =
  'M6 2h8l6 6v14a0 0 0 0 1 0 0H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm8 1.8V8h4.2L14 3.8z';

/**
 * A grid of cells with a heavier header row: a data table. Stroked, so it
 * reads as lighter than the solid program icon beside it in the file list —
 * the point of the pair is that a program and its data are distinguishable at
 * a glance, not that both shout.
 */
export const TABLE =
  'M4 5h16v14H4zM4 9.5h16M10 9.5V19M15 9.5V19';

/** An arrow leaving a tray: upload. Solid. */
export const UPLOAD =
  'M12 3l5 5h-3.2v6h-3.6V8H7l5-5zM4 17h16v3H4v-3z';

/** An arrow landing in a tray: download. Solid. */
export const DOWNLOAD =
  'M12 16l-5-5h3.2V5h3.6v6H17l-5 5zM4 17h16v3H4v-3z';

/** A play triangle. Stroked, to match the toolbar's other outline glyph. */
export const PLAY = 'M8 5.5l10 6.5-10 6.5z';

/** Three quarters of a circle: the spinner, animated by its own CSS. */
export const SPINNER = 'M12 3a9 9 0 1 0 9 9';

/**
 * Which glyph a file in the workspace gets, by extension.
 *
 * A workspace holds two kinds of thing — dPASP programs and the data files
 * they read — and they are used quite differently: one is opened and run, the
 * other is referenced by name from a `#learn` directive or a `#python` block.
 * Telling them apart in the list is worth one icon.
 *
 * The extension is matched case-insensitively, and anything unrecognised gets
 * the plain document rather than a guess.
 */
const PROGRAM_EXTENSIONS = ['.pasp', '.plp', '.lp', '.pl'];
const DATA_EXTENSIONS = ['.csv', '.tsv'];

export interface FileGlyph {
  /** Path data for `Icon`. */
  d: string;
  solid: boolean;
  /** For the icon's tooltip and its `aria-label`. */
  label: string;
}

export function fileGlyph(filename: string): FileGlyph {
  const name = filename.toLowerCase();

  if (DATA_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return { d: TABLE, solid: false, label: 'data file' };
  }
  if (PROGRAM_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return { d: FILE, solid: true, label: 'dPASP program' };
  }
  return { d: FILE, solid: true, label: 'file' };
}
