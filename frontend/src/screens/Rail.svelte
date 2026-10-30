<script lang="ts">
  import Counter from "../components/Counter.svelte";
  import Icon, { type IconName } from "../components/Icon.svelte";
  import Kbd from "../components/Kbd.svelte";
  import Segmented from "../components/Segmented.svelte";
  import * as act from "../lib/actions";
  import { fox } from "../lib/assets";
  import { filterCounts } from "../lib/filters";
  import { language, t } from "../lib/i18n.svelte";
  import { play } from "../lib/sound";
  import { app, saveSettings, setFilter, setLanguage, type Page } from "../lib/store.svelte";

  let { onpalette }: { onpalette: () => void } = $props();

  const running = $derived(app.rows.filter((r) => r.running).length);
  const filters = $derived(filterCounts(app.rows));
  const pages: { id: Page; icon: IconName; label: string }[] = $derived([
    { id: "profiles", icon: "users", label: t("nav_profiles") },
    { id: "log", icon: "log", label: t("activity_log") },
    { id: "agents", icon: "bot", label: t("nav_agents") },
    { id: "settings", icon: "cog", label: t("settings") },
  ]);

  function filterLabel(id: string): string {
    if (id.startsWith("tag:")) return `#${id.slice(4)}`;
    if (id.startsWith("status:")) return t(`status_${id.slice(7)}`);
    return t(`filter_${id}`);
  }

  function go(page: Page) {
    if (app.page === page) return;
    app.page = page;
    play("toggle");
  }
</script>

<nav class="rail">
  <div class="brand">
    <img src={fox} alt="" class="logo" />
    <div>
      <div class="display name">CloutFox</div>
      <div class="mono tag">{t("app_subtitle")}</div>
    </div>
  </div>

  <div class="stats">
    <div class="stat">
      <span class="num display"><Counter value={app.rows.length} /></span>
      <span class="label">{t("stat_profiles")}</span>
    </div>
    <div class="stat" class:live={running > 0}>
      <span class="num display"><Counter value={running} /></span>
      <span class="label">{t("stat_running")}</span>
    </div>
  </div>

  <button type="button" class="primary" data-press onclick={act.create}>
    <Icon name="plus" size={18} />
    <span>{t("new_profile")}</span>
    <Kbd keys="N" />
  </button>
  <div class="quick">
    <button type="button" data-press title={t("bulk_create_btn")} onclick={act.bulkCreate}><Icon name="layers" size={16} /><span>{t("bulk_short")}</span></button>
    <button type="button" data-press title={t("import")} onclick={act.importProfiles}><Icon name="import" size={16} /><span>{t("import")}</span></button>
    <button type="button" data-press title={t("export")} onclick={() => act.exportProfiles()}><Icon name="export" size={16} /><span>{t("export")}</span></button>
  </div>

  <ul class="pages">
    {#each pages as p (p.id)}
      <li>
        <button type="button" class:on={app.page === p.id} data-press onclick={() => go(p.id)}>
          <Icon name={p.icon} size={17} />
          <span>{p.label}</span>
          {#if p.id === "agents" && app.help.length}<i class="ping"></i>{/if}
        </button>
      </li>
    {/each}
  </ul>

  <div class="filters">
    <span class="label head">{t("filter_title")}</span>
    <ul>
      {#each filters as f (f.id)}
        <li>
          <button
            type="button"
            class:on={app.filter === f.id}
            data-press
            onclick={() => {
              setFilter(f.id);
              app.page = "profiles";
            }}
          >
            <span class="fname">{filterLabel(f.id)}</span>
            <span class="fcount mono">{f.count}</span>
          </button>
        </li>
      {/each}
    </ul>
  </div>

  <div class="foot">
    <button type="button" class="cmd" data-press onclick={onpalette}>
      <Icon name="command" size={15} />
      <span>{t("palette_open")}</span>
      <Kbd keys="Ctrl+K" />
    </button>
    <div class="row">
      <Segmented
        dark
        value={language()}
        options={[
          { value: "ru", label: "RU" },
          { value: "en", label: "EN" },
        ]}
        onchange={(v) => setLanguage(v)}
      />
      <button
        type="button"
        class="sound"
        class:off={!app.settings?.sound}
        title={app.settings?.sound ? t("sound_off") : t("sound_on")}
        data-press
        onclick={async () => {
          await saveSettings({ sound: !app.settings?.sound });
          play("toggle");
        }}
      >
        <Icon name={app.settings?.sound ? "volume" : "mute"} size={17} />
      </button>
    </div>
    <span class="ver mono">v{app.version}</span>
  </div>
</nav>

<style>
  .rail {
    width: 256px;
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 18px;
    padding: 20px 16px 14px;
    background: var(--rail);
    color: var(--rail-ink);
    border-right: var(--t-border-w) solid var(--t-line);
    overflow: hidden;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .logo {
    width: 46px;
    height: 46px;
    transition: transform 0.6s var(--t-ease);
  }
  .brand:hover .logo {
    transform: rotate(-12deg) scale(1.1);
  }
  .name {
    font-size: 24px;
  }
  .tag {
    margin-top: 3px;
    font-size: 10.5px;
    color: var(--rail-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .stats {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    border: 2px solid var(--rail-line);
  }
  .stat {
    display: grid;
    gap: 4px;
    padding: 10px 12px;
  }
  .stat + .stat {
    border-left: 2px solid var(--rail-line);
  }
  .num {
    font-size: 34px;
  }
  .stat .label {
    color: var(--rail-muted);
    font-size: 10px;
  }
  .stat.live {
    background: var(--live);
  }
  .stat.live .label {
    color: #dfe7ff;
  }
  .primary {
    display: flex;
    align-items: center;
    gap: 10px;
    height: 46px;
    padding: 0 12px;
    border: 2px solid var(--t-accent);
    background: var(--t-accent);
    color: var(--t-fg);
    box-shadow: 5px 5px 0 var(--t-accent-2);
    font: 600 12.5px var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    transition:
      transform var(--t-dur) var(--t-ease),
      box-shadow var(--t-dur) var(--t-ease);
  }
  .primary span {
    flex: 1;
    text-align: left;
  }
  .primary:hover {
    transform: translate(-2px, -2px) rotate(-1deg);
    box-shadow: 7px 7px 0 var(--t-accent-2);
  }
  .primary:active {
    transform: translate(5px, 5px);
    box-shadow: none;
  }
  .quick {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 6px;
    margin-top: -6px;
  }
  .quick button {
    display: grid;
    justify-items: center;
    gap: 4px;
    padding: 8px 2px 7px;
    border: 2px solid var(--rail-line);
    background: var(--rail-deep);
    color: var(--rail-ink);
    font: 600 9.5px var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    transition:
      border-color 0.12s linear,
      transform var(--t-dur) var(--t-ease);
  }
  .quick button span {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .quick button:hover {
    border-color: var(--t-accent);
    color: var(--t-accent);
    transform: translateY(-2px);
  }
  .pages,
  .filters ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .pages {
    display: grid;
    gap: 2px;
  }
  .pages button {
    position: relative;
    width: 100%;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 9px 10px;
    border: 0;
    background: none;
    color: var(--rail-ink);
    font: 600 12px var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    text-align: left;
    transition:
      background-color 0.12s linear,
      padding var(--t-dur) var(--t-ease);
  }
  .pages button:hover {
    padding-left: 16px;
    color: var(--t-accent);
  }
  .pages button.on {
    background: var(--t-accent);
    color: var(--t-fg);
    padding-left: 16px;
  }
  .ping {
    position: absolute;
    right: 10px;
    width: 10px;
    height: 10px;
    background: var(--t-accent-2);
    animation: blink 0.8s steps(1) infinite;
    animation-play-state: var(--loops);
  }
  .filters {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 14px;
    border-top: 2px solid var(--rail-line);
  }
  .head {
    color: var(--rail-muted);
    font-size: 10px;
  }
  .filters ul {
    overflow: auto;
    margin-right: -8px;
    padding-right: 8px;
  }
  .filters ul::-webkit-scrollbar-track {
    background: var(--rail);
    border-left: 0;
  }
  .filters ul::-webkit-scrollbar-thumb {
    background: var(--rail-line);
    border-color: var(--rail);
  }
  .filters button {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border: 0;
    background: none;
    color: var(--rail-ink);
    font-size: 13px;
    text-align: left;
  }
  .filters button:hover .fname {
    text-decoration: underline;
    text-decoration-thickness: 2px;
    text-underline-offset: 3px;
    text-decoration-color: var(--t-accent-2);
  }
  .fname {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .fcount {
    min-width: 28px;
    padding: 1px 5px;
    border: 1.5px solid var(--rail-line);
    font-size: 11px;
    text-align: center;
    color: var(--rail-muted);
  }
  .filters button.on {
    background: var(--rail-deep);
    box-shadow: inset 4px 0 0 var(--t-accent);
  }
  .filters button.on .fcount {
    background: var(--t-accent);
    border-color: var(--t-accent);
    color: var(--t-fg);
  }
  .foot {
    display: grid;
    gap: 10px;
    padding-top: 12px;
    border-top: 2px solid var(--rail-line);
  }
  .cmd {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 8px;
    border: 2px dashed var(--rail-line);
    background: none;
    color: var(--rail-muted);
    font: 600 10.5px var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .cmd span {
    flex: 1;
    text-align: left;
  }
  .cmd:hover {
    border-color: var(--t-accent);
    color: var(--t-accent);
  }
  .row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px;
  }
  .sound {
    width: 38px;
    display: grid;
    place-items: center;
    border: 2px solid var(--rail-line);
    background: var(--rail-deep);
    color: var(--t-accent);
  }
  .sound.off {
    color: var(--rail-muted);
  }
  .sound:hover {
    border-color: var(--t-accent);
  }
  .ver {
    font-size: 10px;
    color: var(--rail-line);
  }
</style>
