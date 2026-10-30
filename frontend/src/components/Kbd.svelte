<script lang="ts">
  let { keys }: { keys: string } = $props();
</script>

<span class="kbd">{#each keys.split("+") as k, i (i)}<kbd>{k}</kbd>{/each}</span>

<style>
  .kbd {
    display: inline-flex;
    gap: 3px;
  }
  kbd {
    min-width: 20px;
    padding: 1px 5px;
    border: 1.5px solid currentColor;
    box-shadow: 2px 2px 0 currentColor;
    font: 600 10.5px/1.4 var(--font-mono);
    text-align: center;
    text-transform: uppercase;
  }
</style>
