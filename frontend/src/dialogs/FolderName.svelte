<script lang="ts">
  import { untrack } from "svelte";
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import Input from "../components/Input.svelte";
  import Modal from "../components/Modal.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { toast } from "../lib/toast.svelte";

  // Create a folder under `parent`, or rename the one at `path`.
  let {
    path = "",
    parent = "",
    close,
  }: { path?: string; parent?: string; close: (v?: boolean) => void } = $props();

  const renaming = untrack(() => Boolean(path));
  let value = $state(untrack(() => (path ? path : parent ? `${parent}/` : "")));
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function go() {
    const text = value.trim();
    if (!text) return (error = t("validation_folder_empty"));
    busy = true;
    const result = renaming ? await py().folder_rename(path, text) : await py().folder_create(text);
    busy = false;
    if (result.error) return (error = result.error);
    if (result.message) toast(result.message, "ok");
    close(true);
  }
</script>

<Modal
  title={renaming ? t("folder_rename") : t("folder_add")}
  subtitle={t("folder_name_hint")}
  width={460}
  onclose={() => close()}
>
  <Field label={t("folder_name")} {error}>
    <Input bind:value autofocus invalid={Boolean(error)} onenter={go} />
  </Field>
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
    <Button variant="accent" icon="folder" {busy} onclick={go}>
      {renaming ? t("save") : t("folder_add")}
    </Button>
  {/snippet}
</Modal>
