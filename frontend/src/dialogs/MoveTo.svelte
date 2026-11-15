<script lang="ts">
  import Button from "../components/Button.svelte";
  import Icon from "../components/Icon.svelte";
  import Input from "../components/Input.svelte";
  import Modal from "../components/Modal.svelte";
  import { py } from "../lib/bridge";
  import { flatten, folderTree } from "../lib/folders";
  import { t } from "../lib/i18n.svelte";
  import { app } from "../lib/store.svelte";
  import { toast } from "../lib/toast.svelte";

  // Where to put the chosen profiles: an existing folder, the top level, or a new folder.
  let { names, close }: { names: string[]; close: (v?: boolean) => void } = $props();

  const tree = $derived(flatten(folderTree(app.rows, app.options?.folders ?? [])));
  const current = $derived(app.rows.find((r) => r.name === names[0])?.folder ?? "");
  let fresh = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function move(folder: string) {
    busy = true;
    const result = await py().profiles_move(names, folder);
    busy = false;
    if (result.error) return (error = result.error);
    if (result.message) toast(result.message, "ok");
    close(true);
  }

  async function createAndMove() {
    const text = fresh.trim();
    if (!text) return;
    busy = true;
    const created = await py().folder_create(text);
    busy = false;
    if (created.error) return (error = created.error);
    await move(created.path ?? text);
  }
</script>

<Modal title={t("folder_move")} subtitle={t("folder_move_hint", { count: names.length })} width={480} onclose={() => close()}>
  <ul class="list">
    <li>
      <button type="button" class:on={current === ""} data-press disabled={busy} onclick={() => move("")}>
        <Icon name="file" size={15} />
        <span>{t("folder_root")}</span>
        {#if current === ""}<b class="mark">✓</b>{/if}
      </button>
    </li>
    {#each tree as node (node.path)}
      <li>
        <button
          type="button"
          class:on={current === node.path}
          data-press
          style:padding-left="{12 + node.depth * 16}px"
          disabled={busy}
          onclick={() => move(node.path)}
        >
          <Icon name="folder" size={15} />
          <span class="name">{node.name}</span>
          <span class="count mono">{node.count}</span>
          {#if current === node.path}<b class="mark">✓</b>{/if}
        </button>
      </li>
    {/each}
    {#if !tree.length}
      <li class="none">{t("folder_none")}</li>
    {/if}
  </ul>

  <div class="new">
    <Input bind:value={fresh} placeholder={t("folder_add")} onenter={createAndMove} />
    <Button size="sm" icon="plus" disabled={!fresh.trim() || busy} onclick={createAndMove}>{t("folder_add")}</Button>
  </div>
  {#if error}<p class="error">{error}</p>{/if}

  {#snippet actions()}
    <Button variant="ghost" onclick={() => close()}>{t("cancel")}</Button>
  {/snippet}
</Modal>

<style>
  .list {
    max-height: 46vh;
    margin: 0;
    padding: 0;
    overflow: auto;
    border: 2px solid var(--t-line);
    list-style: none;
  }
  .list li + li {
    border-top: 2px solid var(--t-line);
  }
  .list button {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 10px 12px;
    border: 0;
    background: transparent;
    color: var(--t-fg);
    text-align: left;
  }
  .list button:hover:not(:disabled) {
    background: var(--t-bg-2);
  }
  .list button.on {
    background: var(--t-accent);
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .count {
    font-size: 12px;
    color: var(--dim);
  }
  .mark {
    margin-left: 6px;
  }
  .none {
    padding: 12px;
    color: var(--dim);
    font-size: 13px;
  }
  .new {
    display: flex;
    gap: 10px;
    margin-top: 14px;
  }
  .error {
    margin: 10px 0 0;
    color: var(--error);
    font-size: 13px;
  }
</style>
