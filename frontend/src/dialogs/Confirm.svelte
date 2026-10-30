<script lang="ts">
  import Button from "../components/Button.svelte";
  import Modal from "../components/Modal.svelte";
  import { t } from "../lib/i18n.svelte";

  let {
    title,
    body = t("cannot_undo"),
    action = t("delete"),
    danger = true,
    close,
  }: { title: string; body?: string; action?: string; danger?: boolean; close: (v?: boolean) => void } =
    $props();
</script>

<Modal {title} tone={danger ? "danger" : "plain"} width={460} onclose={() => close(false)}>
  <p class="body">{body}</p>
  {#snippet actions()}
    <Button variant="ghost" onclick={() => close(false)}>{t("cancel")}</Button>
    <Button variant={danger ? "danger" : "accent"} icon={danger ? "trash" : "check"} onclick={() => close(true)}>
      {action}
    </Button>
  {/snippet}
</Modal>

<style>
  .body {
    margin: 0;
    font-size: 14.5px;
    line-height: 1.5;
  }
</style>
