<script lang="ts">
  import { untrack } from "svelte";
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import Input from "../components/Input.svelte";
  import Modal from "../components/Modal.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { toast } from "../lib/toast.svelte";

  let { name, close }: { name: string; close: (v?: boolean) => void } = $props();

  let value = $state(untrack(() => `${name}-copy`));
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function go() {
    busy = true;
    const result = await py().profile_clone(name, value);
    busy = false;
    if (result?.error) return (error = result.error);
    toast(t("cloned_profile", { name, new: value.trim() }), "ok");
    close(true);
  }
</script>

<Modal title={t("clone_title")} subtitle={t("clone_subtitle", { name })} width={460} onclose={() => close()}>
  <Field label={t("profile_name")} {error}>
    <Input bind:value autofocus invalid={Boolean(error)} onenter={go} />
  </Field>
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
    <Button variant="accent" icon="copy" {busy} onclick={go}>{t("menu_clone")}</Button>
  {/snippet}
</Modal>
