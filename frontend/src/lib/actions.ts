// What a row, the bulk bar and the command palette can do. Each one asks
// what it needs (password, confirmation) and reports through a toast.

import Activity from "../dialogs/Activity.svelte";
import BulkCreate from "../dialogs/BulkCreate.svelte";
import BulkEdit from "../dialogs/BulkEdit.svelte";
import Clone from "../dialogs/Clone.svelte";
import Confirm from "../dialogs/Confirm.svelte";
import Cookies from "../dialogs/Cookies.svelte";
import Encryption from "../dialogs/Encryption.svelte";
import Export from "../dialogs/Export.svelte";
import PasswordPrompt from "../dialogs/PasswordPrompt.svelte";
import ProfileEditor from "../dialogs/ProfileEditor.svelte";
import Warmup from "../dialogs/Warmup.svelte";
import WireGuard from "../dialogs/WireGuard.svelte";
import { py, type Row } from "./bridge";
import { t } from "./i18n.svelte";
import { open } from "./overlay.svelte";
import { play } from "./sound";
import { app, refresh, selected } from "./store.svelte";
import { report, toast } from "./toast.svelte";

function row(name: string): Row | undefined {
  return app.rows.find((r) => r.name === name);
}

/** Ask for an encrypted profile's own password when it needs one. */
async function unlocked(name: string): Promise<boolean> {
  if (!row(name)?.locked) return true;
  return Boolean(await open<boolean>(PasswordPrompt, { name }));
}

export async function launchOrStop(name: string): Promise<void> {
  const r = row(name);
  if (!r || r.loading) return;
  play(r.running ? "tap" : "launch");
  let result = await py().launch(name);
  if (result.needs_password) {
    if (!(await open<boolean>(PasswordPrompt, { name }))) return;
    result = await py().launch(name);
  }
  report(result);
  void refresh();
}

export async function launchMany(names: string[]): Promise<void> {
  play("launch");
  const result = await py().launch_many(names);
  if (result.skipped) toast(t("bulk_skip_locked", { count: result.skipped }));
  void refresh();
}

export async function stopMany(names: string[]): Promise<void> {
  play("tap");
  await py().stop_many(names);
  void refresh();
}

export function create(): void {
  void open(ProfileEditor, { drawer: true }).then(() => refresh());
}

export function edit(name: string): void {
  void open(ProfileEditor, { name, drawer: true }).then(() => refresh());
}

export function bulkCreate(): void {
  void open(BulkCreate).then(() => refresh());
}

export function bulkEdit(names: string[]): void {
  if (names.length) void open(BulkEdit, { names }).then(() => refresh());
}

export async function remove(names: string[]): Promise<void> {
  const running = names.filter((n) => row(n)?.running);
  if (running.length) toast(t("bulk_skip_running", { count: running.length }));
  const todo = names.filter((n) => !row(n)?.running);
  if (!todo.length) return;
  const ok = await open<boolean>(Confirm, {
    title: todo.length === 1 ? t("confirm_delete_title") : t("confirm_bulk_delete", { count: todo.length }),
    body: todo.length === 1 ? t("confirm_delete_msg", { name: todo[0] }) : t("cannot_undo"),
  });
  if (!ok) return;
  const result = await py().profile_delete(todo);
  for (const n of todo) selected.delete(n);
  toast(t("deleted_count", { count: result.deleted }), "ok");
  void refresh();
}

export async function cookies(name: string): Promise<void> {
  if (!(await unlocked(name))) return;
  void open(Cookies, { name });
}

export function warmup(names: string[]): void {
  if (names.length) void open(Warmup, { names }).then(() => refresh());
}

export function clone(name: string): void {
  void open(Clone, { name }).then(() => refresh());
}

export function activity(name: string): void {
  void open(Activity, { name });
}

export async function wireguard(name: string): Promise<void> {
  if (!(await unlocked(name))) return;
  void open(WireGuard, { name, endpoint: row(name)?.wireguard ?? null }).then(() => refresh());
}

export function encryption(name: string): void {
  void open(Encryption, { name }).then(() => refresh());
}

export async function rotate(name: string): Promise<void> {
  toast(t("rotating_ip", { name }));
  report(await py().rotate(name));
}

export async function importProfiles(): Promise<void> {
  const result = await py().import_profiles();
  if (result.picked) {
    toast(`${t("import_success")}: ${result.imported}/${result.picked}`, result.imported ? "ok" : "error");
    void refresh();
  }
}

export function exportProfiles(preset: string[] = []): void {
  if (app.rows.length) void open(Export, { preset });
}

export function menu(name: string, id: string): void {
  const actions: Record<string, () => void> = {
    warmup: () => warmup([name]),
    clone: () => clone(name),
    activity: () => activity(name),
    encryption: () => encryption(name),
    wireguard: () => void wireguard(name),
    rotate_ip: () => void rotate(name),
    export: () => exportProfiles([name]),
  };
  actions[id]?.();
}
