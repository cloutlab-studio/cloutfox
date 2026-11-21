// Installing an update closes the app: ask first, the same way from the bar and from Settings.

import Confirm from "../dialogs/Confirm.svelte";
import { py } from "./bridge";
import { t } from "./i18n.svelte";
import { open } from "./overlay.svelte";
import { report } from "./toast.svelte";

export async function installUpdate(version: string): Promise<void> {
  const ok = await open<boolean>(Confirm, {
    title: t("update_confirm_title", { version }),
    body: t("update_confirm_body"),
    action: t("update_confirm_action"),
    danger: false,
  });
  if (!ok) return;
  report(await py().update_install());
}

export async function restartApp(): Promise<void> {
  report(await py().restart_app());
}
