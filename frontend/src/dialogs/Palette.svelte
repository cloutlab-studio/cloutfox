<script lang="ts">
  import Icon, { type IconName } from "../components/Icon.svelte";
  import Kbd from "../components/Kbd.svelte";
  import * as act from "../lib/actions";
  import { matches } from "../lib/filters";
  import { t } from "../lib/i18n.svelte";
  import { play } from "../lib/sound";
  import { app, setFilter, type Page } from "../lib/store.svelte";

  // Ctrl+K: find a profile or an action and run it from the keyboard.
  let { close }: { close: () => void } = $props();

  interface Item {
    id: string;
    icon: IconName;
    label: string;
    hint?: string;
    run: () => void;
  }

  let query = $state("");
  let active = $state(0);
  let input = $state<HTMLInputElement>();
  let list = $state<HTMLUListElement>();

  $effect(() => {
    input?.focus();
  });

  const go = (page: Page) => () => (app.page = page);

  const commands: Item[] = [
    { id: "new", icon: "plus", label: t("new_profile"), hint: "N", run: act.create },
    { id: "bulk", icon: "layers", label: t("bulk_create_title"), run: act.bulkCreate },
    { id: "import", icon: "import", label: t("import"), run: act.importProfiles },
    { id: "export", icon: "export", label: t("export_profiles"), run: () => act.exportProfiles() },
    { id: "running", icon: "bolt", label: `${t("filter_title")}: ${t("filter_running")}`, run: () => setFilter("running") },
    { id: "all", icon: "users", label: `${t("filter_title")}: ${t("filter_all")}`, run: () => setFilter("all") },
    { id: "log", icon: "log", label: t("activity_log"), run: go("log") },
    { id: "agents", icon: "bot", label: t("nav_agents"), run: go("agents") },
    { id: "settings", icon: "cog", label: t("settings"), run: go("settings") },
  ];

  const items = $derived.by<Item[]>(() => {
    const q = query.trim().toLowerCase();
    const cmds = commands.filter((c) => !q || c.label.toLowerCase().includes(q));
    const profiles = app.rows
      .filter((r) => q && matches(r, q))
      .slice(0, 8)
      .flatMap<Item>((r) => [
        {
          id: `run:${r.name}`,
          icon: r.running ? "stop" : "play",
          label: t(r.running ? "palette_stop" : "palette_launch", { name: r.name }),
          hint: r.proxy || r.wireguard || "",
          run: () => void act.launchOrStop(r.name),
        },
        { id: `edit:${r.name}`, icon: "edit", label: t("palette_edit", { name: r.name }), run: () => act.edit(r.name) },
      ]);
    return [...profiles, ...cmds];
  });

  $effect(() => {
    void query;
    active = 0;
  });

  function run(item: Item | undefined) {
    if (!item) return;
    close();
    play("tap");
    item.run();
  }

  function key(e: KeyboardEvent) {
    if (e.key === "ArrowDown") active = (active + 1) % Math.max(1, items.length);
    else if (e.key === "ArrowUp") active = (active - 1 + items.length) % Math.max(1, items.length);
    else if (e.key === "Enter") run(items[active]);
    else return;
    e.preventDefault();
    list?.querySelector(`[data-i="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }
</script>

<div class="palette" role="dialog" aria-modal="true" aria-label={t("palette_open")}>
  <label class="field">
    <Icon name="command" size={20} />
    <input bind:this={input} bind:value={query} placeholder={t("palette_hint")} spellcheck="false" onkeydown={key} />
    <Kbd keys="Esc" />
  </label>
  <ul bind:this={list}>
    {#each items as item, i (item.id)}
      <li>
        <button
          type="button"
          class:on={i === active}
          data-i={i}
          data-press
          style:animation-delay="{Math.min(i, 10) * 18}ms"
          onmouseenter={() => (active = i)}
          onclick={() => run(item)}
        >
          <Icon name={item.icon} size={16} />
          <span class="text">{item.label}</span>
          {#if item.hint}<span class="hint mono">{item.hint}</span>{/if}
        </button>
      </li>
    {:else}
      <li class="none">{t("palette_empty")}</li>
    {/each}
  </ul>
</div>

<style>
  .palette {
    align-self: start;
    margin-top: 12vh;
    width: min(640px, calc(100vw - 48px));
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: 10px 10px 0 var(--t-accent);
    animation: pop 0.35s var(--t-ease);
  }
  .field {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 16px;
    height: 60px;
    border-bottom: var(--t-border-w) solid var(--t-line);
  }
  input {
    flex: 1;
    border: 0;
    outline: none;
    background: none;
    font-size: 18px;
    user-select: text;
  }
  .field :global(.kbd) {
    color: var(--dim);
  }
  ul {
    max-height: 50vh;
    overflow: auto;
    margin: 0;
    padding: 6px 0;
    list-style: none;
  }
  button {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    border: 0;
    background: none;
    text-align: left;
    font-size: 14.5px;
    animation: rise 0.25s var(--t-ease-out) backwards;
  }
  button.on {
    background: var(--t-accent);
    box-shadow: inset 6px 0 0 var(--t-fg);
  }
  .text {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .hint {
    font-size: 11.5px;
    color: var(--dim);
  }
  .none {
    padding: 18px 16px;
    color: var(--dim);
  }
  @keyframes pop {
    from {
      opacity: 0;
      transform: translateY(-16px) scale(0.97);
    }
  }
</style>
