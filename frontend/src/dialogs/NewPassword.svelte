<script lang="ts">
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import Input from "../components/Input.svelte";
  import Modal from "../components/Modal.svelte";
  import Warning from "../components/Warning.svelte";
  import type { Result } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";

  let {
    title,
    hint = "",
    warning = null,
    allowEmpty = false,
    submitLabel = t("save_changes"),
    forced = false,
    submit,
    close,
  }: {
    title: string;
    hint?: string;
    warning?: string | null;
    allowEmpty?: boolean;
    submitLabel?: string;
    forced?: boolean;
    submit: (password: string) => Promise<Result>;
    close: (v?: Result) => void;
  } = $props();

  let first = $state("");
  let second = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function save() {
    error = null;
    if (!first && !allowEmpty) return (error = t("password_required"));
    if (first !== second) return (error = t("password_mismatch"));
    busy = true;
    const result = await submit(first);
    busy = false;
    if (result.error) error = result.error;
    else close(result);
  }
</script>

<Modal {title} subtitle={hint} width={460} onclose={forced ? undefined : () => close()}>
  {#if warning}<Warning text={warning} />{/if}
  <Field label={t("password_new")}>
    <Input bind:value={first} type="password" reveal autofocus onenter={save} />
  </Field>
  <Field label={t("password_repeat")} {error}>
    <Input bind:value={second} type="password" reveal invalid={Boolean(error)} onenter={save} />
  </Field>
  {#snippet actions()}
    {#if !forced}<Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>{/if}
    <Button variant="accent" icon="lock" {busy} onclick={save}>{submitLabel}</Button>
  {/snippet}
</Modal>
