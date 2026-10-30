<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../components/Button.svelte";
  import Modal from "../components/Modal.svelte";
  import Warning from "../components/Warning.svelte";
  import { py, type EncryptionInfo } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { open } from "../lib/overlay.svelte";
  import { report } from "../lib/toast.svelte";
  import Confirm from "./Confirm.svelte";
  import NewPassword from "./NewPassword.svelte";
  import PasswordPrompt from "./PasswordPrompt.svelte";

  let { name, close }: { name: string; close: () => void } = $props();
  let info = $state<EncryptionInfo | null>(null);
  let busy = $state(false);

  onMount(async () => {
    info = await py().encryption_info(name);
  });

  const protection = $derived(
    !info
      ? ""
      : info.key_by.includes("master") && info.key_by.includes("password")
        ? t("protected_by_both")
        : info.key_by.includes("master")
          ? t("protected_by_master")
          : t("protected_by_password"),
  );
  const hint = $derived(info?.master ? t("encrypt_hint_master", { name }) : t("encrypt_hint_password", { name }));

  async function withKey(): Promise<boolean> {
    if (!info?.needs_password) return true;
    return Boolean(await open<boolean>(PasswordPrompt, { name }));
  }

  async function encrypt() {
    const result = await open(NewPassword, {
      title: t("encrypt_title"),
      hint,
      allowEmpty: info?.master,
      submitLabel: t("encrypt_btn"),
      warning: info?.ram ? null : t("encryption_disk_warning"),
      submit: (pw: string) => py().encrypt(name, pw),
    });
    if (result) {
      report(result);
      close();
    }
  }

  async function changePassword() {
    if (!(await withKey())) return;
    const result = await open(NewPassword, {
      title: t("profile_password_title"),
      hint,
      allowEmpty: info?.master,
      submit: (pw: string) => py().set_profile_password(name, pw),
    });
    if (result) {
      report(result);
      close();
    }
  }

  async function decrypt() {
    const ok = await open<boolean>(Confirm, {
      title: t("decrypt_btn") + "?",
      body: t("confirm_decrypt", { name }),
      action: t("decrypt_btn"),
    });
    if (!ok || !(await withKey())) return;
    busy = true;
    report(await py().decrypt(name));
    busy = false;
    close();
  }
</script>

<Modal title={t("menu_encryption")} subtitle={name} width={520} onclose={close}>
  {#if info && !info.encrypted}
    <p>{hint}</p>
    {#if !info.ram}<Warning text={t("encryption_disk_warning")} />{/if}
  {:else if info}
    <p class="prot">{protection}</p>
    {#if !info.ram}<Warning text={t("encryption_disk_warning")} />{/if}
  {/if}
  {#snippet actions()}
    <Button variant="ghost" onclick={close}>{t("close_btn")}</Button>
    {#if info && !info.encrypted}
      <Button variant="accent" icon="lock" onclick={encrypt}>{t("encrypt_btn")}</Button>
    {:else if info}
      <Button icon="key" onclick={changePassword}>{t("profile_password_title")}</Button>
      <Button variant="danger" icon="unlock" {busy} onclick={decrypt}>{t("decrypt_btn")}</Button>
    {/if}
  {/snippet}
</Modal>

<style>
  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
  }
  .prot {
    padding: 12px 14px;
    border: 2px solid var(--t-line);
    background: var(--live-tint);
    font-weight: 600;
  }
</style>
