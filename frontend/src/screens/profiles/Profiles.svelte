<script lang="ts">
  import Button from "../../components/Button.svelte";
  import Checkbox from "../../components/Checkbox.svelte";
  import Icon from "../../components/Icon.svelte";
  import Kbd from "../../components/Kbd.svelte";
  import * as act from "../../lib/actions";
  import { visible } from "../../lib/filters";
  import { language, t } from "../../lib/i18n.svelte";
  import { play } from "../../lib/sound";
  import { app, selected } from "../../lib/store.svelte";
  import BulkBar from "./BulkBar.svelte";
  import Empty from "./Empty.svelte";
  import ProfileRow from "./ProfileRow.svelte";
  import Ticker from "./Ticker.svelte";

  let { search = $bindable() }: { search?: HTMLInputElement } = $props();

  const rows = $derived(visible(app.rows, app.filter, app.query));
  const running = $derived(app.rows.filter((r) => r.running).length);
  const allPicked = $derived(rows.length > 0 && rows.every((r) => selected.has(r.name)));
  const somePicked = $derived(rows.some((r) => selected.has(r.name)));
  const title = $derived(t("your_profiles"));

  function pickAll(on: boolean) {
    for (const r of rows) on ? selected.add(r.name) : selected.delete(r.name);
  }

  function clearFilters() {
    app.filter = "all";
    app.query = "";
    app.wave++;
    play("toggle");
  }
</script>

<section class="page">
  <Ticker />
  <header class="top">
    <div>
      <h1 class="display title" aria-label={title}>
        {#key language()}
          {#each title.split("") as ch, i (i)}<span style:animation-delay="{i * 35}ms">{ch === " " ? " " : ch}</span>{/each}
        {/key}
      </h1>
      <p class="sub">
        {t("profiles_configured", { count: app.rows.length })} ·
        {#if running}<b class="live">{running}</b> {t("profiles_running_suffix")}{:else}{t("profiles_none_running")}{/if}
      </p>
    </div>
    <div class="tools">
      <label class="search">
        <Icon name="search" size={17} />
        <input
          bind:this={search}
          bind:value={app.query}
          placeholder={t("search_hint")}
          spellcheck="false"
          oninput={() => app.wave++}
          onkeydown={(e) => {
            if (e.key === "Escape" && app.query) {
              e.stopPropagation();
              app.query = "";
            }
          }}
        />
        <Kbd keys="/" />
      </label>
      <Button icon="plus" variant="accent" onclick={act.create}>{t("new_profile")}</Button>
    </div>
  </header>

  <div class="sheet" role="table">
    {#if app.rows.length === 0 && app.loaded}
      <Empty onclick={act.create} />
    {:else}
      <div class="head" role="row">
        <div>
          <Checkbox
            checked={allPicked}
            indeterminate={!allPicked && somePicked}
            title={allPicked ? t("deselect_page") : t("select_page")}
            onchange={pickAll}
          />
        </div>
        <span class="label">{t("col_profile")}</span>
        <span class="label">{t("col_device")}</span>
        <span class="label">{t("col_proxy")}</span>
        <span class="label geo">{t("col_geo")}</span>
        <span class="label">{t("col_status")}</span>
        <span class="label right">{rows.length}/{app.rows.length}</span>
      </div>
      <div class="body">
        {#key app.wave}
          {#each rows as row, i (row.name)}
            <ProfileRow {row} index={i} />
          {:else}
            <div class="none">
              <p class="display">{app.query ? t("no_search_results", { query: app.query }) : t("no_filter_results")}</p>
              <Button onclick={clearFilters}>{t("clear_filters")}</Button>
            </div>
          {/each}
        {/key}
      </div>
    {/if}
  </div>
  <BulkBar />
</section>

<style>
  .page {
    position: relative;
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 0 32px 28px;
    min-width: 0;
  }
  .top {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    flex-wrap: wrap;
  }
  .title {
    margin: 0;
    font-size: 64px;
  }
  .title span {
    display: inline-block;
    animation: drop 0.6s var(--t-ease) backwards;
  }
  .sub {
    margin: 10px 0 0;
    font: 400 13px var(--font-mono);
    color: var(--t-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .live {
    color: var(--live);
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .search {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 340px;
    height: 42px;
    padding: 0 10px 0 12px;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard-sm);
    transition:
      box-shadow var(--t-dur) var(--t-ease),
      transform var(--t-dur) var(--t-ease);
  }
  .search:focus-within {
    box-shadow: 6px 6px 0 var(--t-focus);
    transform: translate(-2px, -2px);
  }
  .search input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: none;
    background: none;
    font-size: 14px;
    user-select: text;
  }
  .search :global(.kbd) {
    color: var(--dim);
  }
  .sheet {
    container: sheet / inline-size;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard);
  }
  .head,
  .body {
    --cols: 28px minmax(120px, 1.25fr) minmax(140px, 1.1fr) minmax(140px, 1.1fr) minmax(100px, 0.9fr) 104px 262px;
  }
  /* A narrow window drops the geo column first; the rest keeps two lines. */
  @container sheet (max-width: 1040px) {
    .head,
    .body {
      --cols: 28px minmax(110px, 1.2fr) minmax(130px, 1fr) minmax(130px, 1fr) 100px 262px;
    }
    .head .geo,
    .body :global(.cell.geo) {
      display: none;
    }
  }
  .head {
    display: grid;
    grid-template-columns: var(--cols);
    align-items: center;
    gap: 12px;
    height: 42px;
    padding: 0 16px 0 14px;
    border-bottom: var(--t-border-w) solid var(--t-line);
    background: var(--t-bg-2);
  }
  .right {
    text-align: right;
  }
  .body {
    flex: 1;
    overflow: auto;
    padding-bottom: 80px;
  }
  .none {
    display: grid;
    justify-items: center;
    gap: 18px;
    padding: 64px 24px;
    text-align: center;
  }
  .none p {
    margin: 0;
    font-size: 28px;
    max-width: 640px;
  }
  @keyframes drop {
    from {
      opacity: 0;
      transform: translateY(-50%) rotate(-6deg);
    }
  }
</style>
