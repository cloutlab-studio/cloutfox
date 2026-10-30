<script lang="ts">
  import { onMount } from "svelte";
  import Button from "../components/Button.svelte";
  import Field from "../components/Field.svelte";
  import Modal from "../components/Modal.svelte";
  import Select from "../components/Select.svelte";
  import Textarea from "../components/Textarea.svelte";
  import { py } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";
  import { open } from "../lib/overlay.svelte";
  import { app } from "../lib/store.svelte";
  import { toast } from "../lib/toast.svelte";
  import PasswordPrompt from "./PasswordPrompt.svelte";

  let { names, close }: { names: string[]; close: (v?: boolean) => void } = $props();
  let busy = $state(false);

  let count = $state("10");
  let shared = $state(0);
  let own = $state("");
  let error = $state<string | null>(null);

  onMount(async () => {
    const info = await py().warmup_info();
    count = String(info.count);
    shared = info.shared;
  });

  const counts = $derived(
    [...new Set([...(app.options?.warmup_counts ?? [3, 5, 10, 15, 20, 30]), Number(count)])].sort((a, b) => a - b),
  );

  async function start() {
    error = null;
    if (!own.trim() && !shared) return (error = t("warmup_no_sites"));
    busy = true;
    let result = await py().warmup(names, own, Number(count));
    if (result.needs_password) {
      // One stopped profile with its own password: ask, then go.
      if (await open<boolean>(PasswordPrompt, { name: result.needs_password })) {
        result = await py().warmup(names, own, Number(count));
      } else {
        busy = false;
        return;
      }
    }
    busy = false;
    if (result.error) return (error = result.error);
    toast(t("warmup_title") + ": " + t("warmup_target_many", { count: result.started ?? 0 }), "info");
    close(true);
  }
</script>

<Modal
  title={t("warmup_title")}
  subtitle={names.length === 1 ? t("warmup_target_one", { name: names[0] }) : t("warmup_target_many", { count: names.length })}
  width={520}
  onclose={() => close()}
>
  <Field label={t("warmup_count")}>
    <Select bind:value={count} options={counts.map((n) => ({ value: String(n), label: t("warmup_count_n", { n }) }))} />
  </Field>
  <Field label={t("warmup_own_list")} hint={t("warmup_own_hint", { count: shared })} {error}>
    <Textarea bind:value={own} rows={5} mono placeholder="example.com" />
  </Field>
  <p class="info">{t("warmup_info")}</p>
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
    <Button variant="accent" icon="flame" {busy} onclick={start}>{t("warmup_start")}</Button>
  {/snippet}
</Modal>

<style>
  .info {
    margin: 0;
    padding: 12px 14px;
    border-left: 6px solid var(--t-accent);
    background: var(--t-bg);
    font-size: 13px;
    line-height: 1.5;
  }
</style>
