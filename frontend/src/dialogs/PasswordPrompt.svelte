<script lang="ts">
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import Input from "../components/Input.svelte";
  import Modal from "../components/Modal.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";

  let { name, close }: { name: string; close: (v?: boolean) => void } = $props();

  let password = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function go() {
    if (!password) return (error = t("password_required"));
    busy = true;
    const result = await py().profile_unlock(name, password);
    busy = false;
    if (result.error) error = result.error;
    else close(true);
  }
</script>

<Modal title={t("profile_locked_title")} subtitle={name} width={420} onclose={() => close(false)}>
  <Field label={t("password")} {error}>
    <Input bind:value={password} type="password" reveal autofocus invalid={Boolean(error)} onenter={go} />
  </Field>
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close(false)}>{t("cancel")}</Button>
    <Button variant="accent" icon="unlock" {busy} onclick={go}>{t("lock_open")}</Button>
  {/snippet}
</Modal>
