<script lang="ts">
  import Checkbox from "../../components/Checkbox.svelte";
  import Icon from "../../components/Icon.svelte";
  import IconButton from "../../components/IconButton.svelte";
  import Menu, { type MenuItem } from "../../components/Menu.svelte";
  import Stamp from "../../components/Stamp.svelte";
  import * as act from "../../lib/actions";
  import type { Row } from "../../lib/bridge";
  import { exitIp, OS_LABELS } from "../../lib/format";
  import { t } from "../../lib/i18n.svelte";
  import { stagger } from "../../lib/motion";
  import { selected } from "../../lib/store.svelte";
  import LaunchButton from "./LaunchButton.svelte";

  let { row, index }: { row: Row; index: number } = $props();

  const busy = $derived(row.running || row.loading);
  const exit = $derived(exitIp(row));
  const detail = $derived(row.tags.map((tag) => `#${tag}`).join(" ") || row.notes.split("\n", 1)[0]);
  const items = $derived<MenuItem[]>([
    { id: "warmup", label: t("menu_warmup"), icon: "flame", disabled: busy },
    { id: "clone", label: t("menu_clone"), icon: "copy" },
    { id: "activity", label: t("menu_activity"), icon: "bot" },
    { id: "encryption", label: t("menu_encryption"), icon: "lock", disabled: busy || row.temporary },
    { id: "wireguard", label: t("menu_wireguard"), icon: "tunnel", disabled: busy || row.temporary },
    { id: "export", label: t("export_profile"), icon: "export", disabled: row.temporary },
    ...(row.rotate ? [{ id: "rotate_ip", label: t("menu_rotate_ip"), icon: "refresh" as const }] : []),
  ]);
</script>

<div
  class="row"
  class:live={row.running}
  class:picked={selected.has(row.name)}
  class:failed={row.failed && !row.running && !row.loading}
  style:animation-delay={stagger(index)}
  role="row"
>
  <div class="cell select">
    <Checkbox
      checked={selected.has(row.name)}
      title={t("tooltip_select")}
      onchange={(v) => (v ? selected.add(row.name) : selected.delete(row.name))}
    />
  </div>

  <div class="cell">
    <div class="first">
      {#if row.encrypted}<span class="lock" title={t("encrypted_short")}><Icon name="lock" size={14} /></span>{/if}
      <button type="button" class="name" title={row.notes || row.name} onclick={() => act.edit(row.name)}>{row.name}</button>
    </div>
    <div class="second">
      {#if row.status}
        <span class="badge {row.status}">{t(`status_${row.status}`)}</span>
      {/if}
      {#if row.temporary}<span class="minor">{t("temporary_short")}</span>{/if}
      {#if detail}
        <span class="minor ellipsis">{detail}</span>
      {:else if !row.status && !row.temporary}
        <span class="minor">{t("no_tags_short")}</span>
      {/if}
    </div>
  </div>

  <div class="cell device">
    <span class="os" title={row.os}>{OS_LABELS[row.os] ?? "OS"}</span>
    <div class="stack">
      <span class="engine" class:chrome={row.engine === "chrome"}>{row.engine === "chrome" ? "Chrome" : "Camoufox"}</span>
      <span class="minor mono ellipsis">
        {row.sealed ? t("encrypted_short") : row.device || t("no_fingerprint_short")}
      </span>
    </div>
  </div>

  <div class="cell">
    {#if row.wireguard}
      <span class="data ellipsis">{row.wireguard}</span>
      <span class="minor mono ellipsis tunnel">
        WIREGUARD{exit ? ` · ${exit}` : row.last.at ? ` · ${t("exit_ip_unknown")}` : ""}
      </span>
    {:else if row.proxy}
      <span class="data ellipsis">{row.proxy}</span>
      <span class="minor mono ellipsis">{row.scheme.toUpperCase()}{exit ? ` · ${exit}` : ""}</span>
    {:else}
      <span class="plain">{t("direct_short")}</span>
      <span class="minor">{t("no_proxy_short")}</span>
    {/if}
  </div>

  <div class="cell geo">
    {#if row.timezone}<span class="data ellipsis">{row.timezone}</span>{:else}<span class="plain dim">{t("follows_ip")}</span>{/if}
    {#if row.locale}<span class="minor mono">{row.locale}</span>{:else}<span class="minor">{t("follows_ip")}</span>{/if}
  </div>

  <div class="cell status"><Stamp {row} /></div>

  <div class="cell actions">
    <LaunchButton {row} onclick={() => act.launchOrStop(row.name)} />
    <IconButton size={32} icon="cookie" title={t("tooltip_cookies")} disabled={busy} onclick={() => act.cookies(row.name)} />
    <IconButton size={32} icon="edit" title={t("tooltip_edit")} onclick={() => act.edit(row.name)} />
    <IconButton size={32} icon="trash" title={t("tooltip_delete")} danger disabled={busy} onclick={() => act.remove([row.name])} />
    <Menu {items} title={t("tooltip_more")} onpick={(id) => act.menu(row.name, id)} />
  </div>
</div>

<style>
  .row {
    position: relative;
    display: grid;
    grid-template-columns: var(--cols);
    align-items: center;
    gap: 12px;
    min-height: 64px;
    padding: 0 16px 0 14px;
    border-bottom: 1px solid var(--t-line);
    background: var(--t-surface);
    animation: rise 0.42s var(--t-ease) backwards;
    transition: background-color 0.12s linear;
  }
  .row::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 0;
    background: var(--live);
    transition: width var(--t-dur) var(--t-ease);
  }
  .row:hover {
    background: var(--hover-row);
  }
  /* An open ⋮ menu sits above the rows below it. */
  .row:has(:global(.menu)) {
    z-index: 5;
  }
  .row.picked {
    background: var(--accent-soft);
  }
  .row.live {
    background: linear-gradient(90deg, var(--live-tint), var(--t-surface) 60%);
  }
  .row.live::before {
    width: 6px;
  }
  .row.failed::before {
    width: 6px;
    background: var(--error);
  }
  .cell {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .select {
    display: flex;
  }
  .first {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }
  .lock {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    background: var(--t-fg);
    color: var(--t-accent);
  }
  .name {
    min-width: 0;
    padding: 0;
    border: 0;
    background: none;
    font-size: 14.5px;
    font-weight: 600;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    background-image: linear-gradient(var(--t-accent), var(--t-accent));
    background-size: 0 45%;
    background-position: 0 85%;
    background-repeat: no-repeat;
    transition: background-size var(--t-dur) var(--t-ease);
  }
  .name:hover {
    background-size: 100% 45%;
  }
  .second {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }
  .badge {
    flex: none;
    padding: 0 4px;
    border: 1px solid currentColor;
    font: 600 9.5px/1.5 var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--t-muted);
  }
  .badge.active {
    color: var(--success);
  }
  .badge.banned {
    color: var(--error);
    text-decoration: line-through;
  }
  .badge.paused {
    color: var(--dim);
  }
  .badge.warming {
    color: var(--warning);
  }
  .minor {
    font-size: 11.5px;
    color: var(--dim);
    white-space: nowrap;
  }
  .ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .data {
    font: 400 13px var(--font-mono);
  }
  .plain {
    font-size: 13px;
    color: var(--t-muted);
  }
  .tunnel {
    color: var(--live);
  }
  .device {
    grid-template-columns: auto 1fr;
    align-items: center;
    gap: 10px;
  }
  .os {
    display: grid;
    place-items: center;
    width: 40px;
    height: 24px;
    border: 2px solid var(--t-line);
    font: 600 11px var(--font-mono);
  }
  .live .os {
    background: var(--t-fg);
    color: var(--t-bg);
  }
  .stack {
    display: grid;
    gap: 2px;
    min-width: 0;
  }
  .engine {
    font-size: 13px;
  }
  .engine.chrome {
    font-weight: 600;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 2px;
    justify-content: flex-end;
  }
  .actions :global(.launch) {
    margin-right: 6px;
  }
</style>
