<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../../components/Button.svelte";
  import Confirm from "../../dialogs/Confirm.svelte";
  import NewPassword from "../../dialogs/NewPassword.svelte";
  import RecoveryKey from "../../dialogs/RecoveryKey.svelte";
  import { py } from "../../lib/bridge";
  import { t } from "../../lib/i18n.svelte";
  import { open } from "../../lib/overlay.svelte";
  import { refresh } from "../../lib/store.svelte";
  import { report, toast } from "../../lib/toast.svelte";
  import Section from "./Section.svelte";

  let { index }: { index: number } = $props();
  let info = $state<{ master: boolean; duress: boolean } | null>(null);

  async function load() {
    info = await py().security_info();
    void refresh();
  }
  onMount(load);

  async function enable() {
    const result = await open<{ key?: string }>(NewPassword, {
      title: t("master_enable"),
      hint: t("master_enable_hint"),
      warning: t("master_forget_warning"),
      submit: (pw: string) => py().enable_master(pw),
    });
    if (!result?.key) return;
    toast(t("master_enabled"), "ok");
    await load();
    await open(RecoveryKey, { key: result.key, sticky: true });
  }

  async function change() {
    const result = await open(NewPassword, { title: t("master_change"), submit: (pw: string) => py().change_master(pw) });
    if (result) toast(t("master_changed"), "ok");
  }

  async function recovery() {
    const { key } = await py().new_recovery_key();
    await open(RecoveryKey, { key, sticky: true });
  }

  async function disable() {
    const ok = await open<boolean>(Confirm, {
      title: t("master_disable"),
      body: t("master_disable_body"),
      action: t("master_disable"),
    });
    if (!ok) return;
    if (report(await py().disable_master())) toast(t("master_disabled"), "ok");
    await load();
  }

  async function duress() {
    const result = await open(NewPassword, {
      title: info?.duress ? t("duress_change") : t("duress_set_title"),
      hint: t("duress_hint"),
      warning: t("duress_warning"),
      submit: (pw: string) => py().set_duress(pw),
    });
    if (result) toast(t("duress_set"), "ok");
    await load();
  }

  async function clearDuress() {
    const ok = await open<boolean>(Confirm, {
      title: t("duress_clear") + "?",
      body: t("confirm_duress_clear"),
      action: t("duress_clear"),
    });
    if (!ok) return;
    report(await py().set_duress(null));
    toast(t("duress_cleared"), "ok");
    await load();
  }
</script>

<Section title={t("settings_security")} icon="lock" {index}>
  {#if info}
    <p class="state">
      {t("master_password")}
      <span class="pill" class:on={info.master}>{info.master ? t("state_on") : t("state_off")}</span>
    </p>
    <p class="hint">{t("master_explain")}</p>
    {#if info.master}
      <div class="buttons">
        <Button size="sm" icon="key" onclick={change}>{t("master_change")}</Button>
        <Button size="sm" icon="key" onclick={recovery}>{t("recovery_new")}</Button>
        <Button size="sm" icon="unlock" variant="danger" onclick={disable}>{t("master_disable")}</Button>
      </div>
      <p class="state">
        {t("duress_password")}
        <span class="pill" class:on={info.duress}>{info.duress ? t("state_set") : t("state_not_set")}</span>
      </p>
      <p class="hint">{t("duress_hint")}</p>
      <div class="buttons">
        <Button size="sm" icon="flame" onclick={duress}>{info.duress ? t("duress_change") : t("duress_set_title")}</Button>
        {#if info.duress}<Button size="sm" icon="close" onclick={clearDuress}>{t("duress_clear")}</Button>{/if}
      </div>
    {:else}
      <div class="buttons">
        <Button variant="accent" size="sm" icon="lock" onclick={enable}>{t("master_enable")}</Button>
      </div>
    {/if}
  {/if}
</Section>
