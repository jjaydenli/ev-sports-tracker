/**
 * True for a bare `/` press that isn't typing: not inside a text field, no Ctrl, Cmd or Alt.
 * Matches on `key`, so layouts where `/` needs Shift still work.
 */
export function isSlashShortcut(event: KeyboardEvent): boolean {
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return false;
  const target = event.target;
  return !(
    target instanceof HTMLElement &&
    (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
  );
}
