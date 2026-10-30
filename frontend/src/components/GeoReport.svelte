<script lang="ts">
  import type { GeoReport } from "../lib/bridge";
  import { t } from "../lib/i18n.svelte";

  let {
    report,
    onlocale,
  }: { report: Partial<GeoReport> & { error?: string }; onlocale?: (value: string) => void } = $props();

  const mode = (pinned: boolean | undefined) => (pinned ? t("geo_pinned") : t("geo_auto"));
</script>

<div class="geo selectable">
  {#if !report.exit_ip}
    <p class="bad">{report.error && report.error.length ? t("geo_check_failed", { error: report.error }) : t("geo_check_failed", { error: "?" })}</p>
  {:else}
    <p class="head mono">{t("geo_exit", { ip: report.exit_ip, country: report.country ?? "?" })}</p>
    <p>{t("geo_timezone", { value: report.timezone ?? "?", mode: mode(report.timezone_pinned) })}</p>
    <p>
      {t("geo_locale", {
        value: report.locale ?? `~${report.suggested_locale ?? "?"}`,
        mode: report.locale_pinned ? t("geo_pinned") : t("geo_locale_random"),
      })}
    </p>
    {#each report.sources ?? [] as s (s.source)}
      <p class="dim mono small">
        {s.error
          ? t("geo_source_error", { source: s.source, error: s.error })
          : t("geo_source", {
              source: s.source,
              ip: s.ip ?? "?",
              country: s.country ?? "?",
              city: s.city ?? "",
              timezone: s.timezone ?? "-",
            })}
      </p>
    {/each}
    {#if report.error}<p class="bad">{report.error}</p>{/if}
    {#each report.warnings ?? [] as w, i (i)}
      <p class="warn">⚠ {w}</p>
    {/each}
    {#if !report.warnings?.length && !report.error}
      <p class="good">✓ {t("geo_all_good")}</p>
    {/if}
    {#if onlocale && report.suggested_locale && !report.locale_pinned}
      <button type="button" class="use" data-press onclick={() => onlocale(report.suggested_locale!)}>
        {t("geo_use_suggested", { value: report.suggested_locale })}
      </button>
    {/if}
  {/if}
</div>

<style>
  .geo {
    display: grid;
    gap: 4px;
    padding: 12px 14px;
    border: 2px solid var(--t-line);
    background: var(--t-bg);
    animation: rise 0.35s var(--t-ease-out);
  }
  p {
    margin: 0;
    font-size: 12.5px;
    overflow-wrap: anywhere;
  }
  .head {
    font-size: 14px;
    font-weight: 600;
  }
  .small {
    font-size: 11.5px;
  }
  .bad {
    color: var(--error);
    font-weight: 600;
  }
  .warn {
    color: var(--warning);
    font-weight: 600;
  }
  .good {
    color: var(--success);
    font-weight: 600;
  }
  .use {
    justify-self: start;
    margin-top: 4px;
    padding: 4px 8px;
    border: 2px solid var(--t-line);
    background: var(--t-accent);
    font: 600 11.5px var(--font-mono);
  }
</style>
