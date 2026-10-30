<script lang="ts">
  import { t } from "../../lib/i18n.svelte";
  import Backups from "./Backups.svelte";
  import Extensions from "./Extensions.svelte";
  import Interface from "./Interface.svelte";
  import Launch from "./Launch.svelte";
  import Security from "./Security.svelte";
  import Warmup from "./WarmupSites.svelte";
</script>

<div class="page">
  <h1 class="display">{t("settings")}</h1>
  <div class="cols">
    <Interface index={0} />
    <Launch index={1} />
    <Security index={2} />
    <Warmup index={3} />
    <Extensions index={4} />
    <Backups index={5} />
  </div>
</div>

<style>
  .page {
    height: 100%;
    overflow: auto;
    padding: 28px 32px 40px;
  }
  h1 {
    margin: 0 0 26px;
    font-size: 64px;
  }
  .cols {
    columns: 2 460px;
    column-gap: 28px;
  }
</style>
